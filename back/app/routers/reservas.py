"""
Reservas: creación sin sobreventa, pagos parciales, cancelación e historial.

Orden al crear (decisión 1b):
  1. Cotizar todo (solo lecturas y validaciones; si algo falla no se ha tocado nada).
  2. Descontar inventario ítem por ítem con escrituras condicionales; si uno falla, compensar.
  3. Insertar la reserva; si el insert falla, devolver todo el inventario.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.cotizacion import (
    cotizar_hotel,
    cotizar_paquete,
    cotizar_tour,
    cotizar_vuelo,
    movimientos_de_reserva,
)
from app.database import get_db
from app.inventario import descontar_todo, devolver_todo
from app.routers.asesores import asesor_activo
from app.schemas import CancelarReserva, Estado, PagoCreate, ReservaCreate, ReservaResponse
from app.utils import a_mongo, a_utc, ahora, buscar_o_404, oid

router = APIRouter()


def _nuevo_codigo(momento) -> str:
    """RV-AAMMDD-XXXX. Sin colección de contadores: el índice único detecta choques y se reintenta."""
    return f"RV-{momento:%y%m%d}-{secrets.token_hex(2).upper()}"


@router.get("/", response_model=list[ReservaResponse])
def listar_reservas(estado: Estado | None = None, ciudad: str | None = None,
                    cliente: str | None = Query(None, description="Documento del cliente"),
                    limite: int = Query(50, ge=1, le=200), db: Database = Depends(get_db)):
    filtro: dict = {}
    if estado:
        filtro["estado"] = estado                       # índice {estado, creada}
    if ciudad:
        filtro["items.ciudad"] = ciudad.upper()         # índice multikey {items.ciudad}
    if cliente:
        filtro["cliente.documento"] = cliente           # gracias a la copia, sin $lookup
    return list(db.reservas.find(filtro).sort("creada", -1).limit(limite))


@router.get("/{codigo}", response_model=ReservaResponse)
def obtener_reserva(codigo: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.reservas, {"codigo": codigo}, "Reserva")


@router.post("/", response_model=ReservaResponse, status_code=201)
def crear_reserva(datos: ReservaCreate, db: Database = Depends(get_db)):
    momento = ahora()
    cliente = buscar_o_404(db.clientes, {"_id": oid(datos.cliente_id)}, "Cliente")
    asesor = buscar_o_404(db.asesores, {"_id": oid(datos.asesor_id)}, "Asesor")
    asesor_activo(db, asesor["codigo"])

    # 1. Cotizar: precios y nombres se COPIAN aquí y quedan congelados en la reserva
    items, movimientos = [], []
    for it in datos.items:
        if it.tipo == "vuelo":
            item, movs = cotizar_vuelo(db, oid(it.ref_id), it.tarifa, it.cantidad, momento)
        elif it.tipo == "hotel":
            item, movs = cotizar_hotel(db, oid(it.ref_id), it.tipo_hab, a_utc(it.entrada),
                                       a_utc(it.salida), it.cantidad, momento)
        elif it.tipo == "tour":
            item, movs = cotizar_tour(db, oid(it.ref_id), oid(it.salida_id), it.cantidad, momento)
        else:
            item, movs = cotizar_paquete(db, oid(it.ref_id), it.cantidad, momento)
        items.append(item)
        movimientos += movs

    # 2. Descontar (SinDisponibilidad -> 409, ver handler en main.py)
    hechos = descontar_todo(db, movimientos)

    # 3. Insertar
    doc = {
        "cliente_id": cliente["_id"],
        "cliente": {"documento": cliente["documento"], "nombre": cliente["nombre"]},
        "asesor_id": asesor["_id"],
        "asesor": asesor["nombre"],
        "creada": momento,
        "estado": "Pendiente",
        "items": items,
        "pasajeros": a_mongo([p.model_dump() for p in datos.pasajeros]),
        "total": sum(i["subtotal"] for i in items),
        "pagado": 0,
        "pagos": [],
        "historial": [{"antes": None, "despues": "Pendiente", "fecha": momento,
                       "usuario": asesor["codigo"]}],
    }
    try:
        for _ in range(5):
            doc["codigo"] = _nuevo_codigo(momento)
            doc.pop("_id", None)
            try:
                db.reservas.insert_one(doc)
                return doc
            except DuplicateKeyError:
                continue
        raise HTTPException(500, "No se pudo generar un código de reserva único")
    except Exception:
        devolver_todo(db, hechos)          # compensación: la reserva no quedó, el inventario vuelve
        raise


@router.post("/{codigo}/pagos", response_model=ReservaResponse)
def registrar_pago(codigo: str, pago: PagoCreate, db: Database = Depends(get_db)):
    """Una sola escritura atómica (update con pipeline) hace lo que pide el modelo:
    $push al pago + $inc a pagado, y si pagado >= total -> Pagada + evento en historial.
    El filtro rechaza pagos a reservas canceladas y pagos que superen el saldo (punto 10)."""
    asesor_activo(db, pago.usuario)
    momento = ahora()
    nuevo_pago = {"fecha": momento, "valor": pago.valor, "medio": pago.medio}
    evento = {"antes": "Pendiente", "despues": "Pagada", "fecha": momento, "usuario": pago.usuario}
    queda_paga = {"$gte": ["$pagado", "$total"]}

    r = db.reservas.find_one_and_update(
        {"codigo": codigo, "estado": {"$ne": "Cancelada"},
         "$expr": {"$lte": [{"$add": ["$pagado", pago.valor]}, "$total"]}},
        [
            {"$set": {"pagos": {"$concatArrays": ["$pagos", [{"$literal": nuevo_pago}]]},
                      "pagado": {"$add": ["$pagado", pago.valor]}}},
            {"$set": {
                "historial": {"$cond": [{"$and": [queda_paga, {"$eq": ["$estado", "Pendiente"]}]},
                                        {"$concatArrays": ["$historial", [{"$literal": evento}]]},
                                        "$historial"]},
                "estado": {"$cond": [queda_paga, "Pagada", "$estado"]},
            }},
        ],
        return_document=ReturnDocument.AFTER,
    )
    if r is None:                                   # explicar por qué no se aplicó
        actual = buscar_o_404(db.reservas, {"codigo": codigo}, "Reserva")
        if actual["estado"] == "Cancelada":
            raise HTTPException(400, "No se aceptan pagos en una reserva cancelada")
        raise HTTPException(400, f"El pago supera el saldo pendiente ({actual['total'] - actual['pagado']})")
    return r


@router.post("/{codigo}/cancelar", response_model=ReservaResponse)
def cancelar_reserva(codigo: str, datos: CancelarReserva, db: Database = Depends(get_db)):
    """Cambia el estado y devuelve el inventario; los pagos quedan como están (decisión punto 10).
    El filtro estado != Cancelada hace la operación idempotente: cancelar dos veces NO
    devuelve el inventario dos veces."""
    asesor_activo(db, datos.usuario)
    momento = ahora()
    r = db.reservas.find_one_and_update(
        {"codigo": codigo, "estado": {"$ne": "Cancelada"}},
        [
            {"$set": {"historial": {"$concatArrays": ["$historial", [{
                "antes": "$estado",                     # estado anterior real, leído en la misma escritura
                "despues": {"$literal": "Cancelada"},
                "fecha": {"$literal": momento},
                "usuario": {"$literal": datos.usuario},
            }]]}}},
            {"$set": {"estado": "Cancelada"}},
        ],
        return_document=ReturnDocument.AFTER,
    )
    if r is None:
        buscar_o_404(db.reservas, {"codigo": codigo}, "Reserva")
        raise HTTPException(400, "La reserva ya estaba cancelada")
    devolver_todo(db, movimientos_de_reserva(db, r))
    return r
