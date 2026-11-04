"""
Reportes B1-B3: se resuelven por completo con pipelines de agregación, así Mongo hace los cálculos
y Python no recorre documentos. Incluso aplanar _id es una etapa $project del pipeline.
"""
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database import get_db
from app.schemas import DestinoVendido, OcupacionVuelo, VentasMes

router = APIRouter()


@router.get("/ventas-por-mes", response_model=list[VentasMes])
def ventas_por_mes(db: Database = Depends(get_db)):
    """B1: total vendido y número de reservas por mes, sin contar canceladas."""
    return list(db.reservas.aggregate([
        {"$match": {"estado": {"$ne": "Cancelada"}}},
        {"$group": {"_id": {"anio": {"$year": "$creada"}, "mes": {"$month": "$creada"}},
                    "total_vendido": {"$sum": "$total"}, "reservas": {"$sum": 1}}},
        {"$sort": {"_id.anio": 1, "_id.mes": 1}},
        {"$project": {"_id": 0, "anio": "$_id.anio", "mes": "$_id.mes",
                      "total_vendido": 1, "reservas": 1}},
    ]))


@router.get("/destinos-mas-vendidos", response_model=list[DestinoVendido])
def destinos_mas_vendidos(db: Database = Depends(get_db)):
    """B2: las 5 ciudades de destino con más ingresos, sin contar canceladas."""
    # El enunciado dice "las 5 ciudades de destino con más ingresos, con el número de pasajeros de
    # cada una" y no define cómo contar pasajeros. Esta métrica es una interpretación por ítems, no
    # un conteo de personas únicas verificadas: una reserva con ida y regreso, o con vuelo+paquete,
    # puede contar a la misma persona más de una vez.
    # Interpretación: ingresos = subtotal de TODOS los ítems de la ciudad; pasajeros = cantidad solo
    # de los ítems vuelo y paquete, que son los que representan personas viajando hacia el destino.
    return list(db.reservas.aggregate([
        {"$match": {"estado": {"$ne": "Cancelada"}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.ciudad",
                    "ingresos": {"$sum": "$items.subtotal"},
                    "pasajeros": {"$sum": {"$cond": [
                        {"$in": ["$items.tipo", ["vuelo", "paquete"]]}, "$items.cantidad", 0]}}}},
        {"$sort": {"ingresos": -1}},
        {"$limit": 5},
        {"$project": {"_id": 0, "ciudad": "$_id", "ingresos": 1, "pasajeros": 1}},
    ]))


@router.get("/ocupacion-vuelos", response_model=list[OcupacionVuelo])
def ocupacion_vuelos(db: Database = Depends(get_db)):
    """B3: ocupación por vuelo. Sale del inventario, que ya excluye las canceladas porque
    cancelar devuelve las sillas a `libres`."""
    return list(db.vuelos.aggregate([
        {"$project": {"codigo": 1, "sillas_totales": {"$sum": "$tarifas.sillas"},
                      "vendidas": {"$sum": {"$map": {"input": "$tarifas", "as": "t",
                          "in": {"$subtract": ["$$t.sillas", "$$t.libres"]}}}}}},
        {"$project": {"codigo": 1, "sillas_totales": 1, "vendidas": 1,
                      "ocupacion_pct": {"$cond": [{"$eq": ["$sillas_totales", 0]}, 0,   # vuelo sin tarifas
                          {"$round": [{"$multiply": [{"$divide": ["$vendidas", "$sillas_totales"]}, 100]}, 1]}]}}},
        {"$sort": {"ocupacion_pct": -1}},
    ]))
