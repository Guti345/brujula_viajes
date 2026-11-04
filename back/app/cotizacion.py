"""
app/cotizacion.py — Convierte lo que pide el cliente en (a) el ítem que se guarda, con nombre,
ciudad, fechas y precio CONGELADOS (REF + COPIA), y (b) los movimientos de inventario.

Reglas acordadas en el Módulo 0:
  * precio por persona; subtotal = cantidad × precio                      (punto 5)
  * hotel: precio = precio_noche × noches; habitaciones = ceil(personas / capacidad)
  * paquete: precio = round(Σ precios copiados × (1 − descuento/100))     (pesos enteros)
"""
from datetime import datetime, timedelta
from math import ceil

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from .inventario import Movimiento
from .utils import a_utc, buscar_o_404

# ───────────────────────────── Lecturas con validación ─────────────────────────────


def _tarifa(vuelo: dict, nombre: str) -> dict:
    for t in vuelo.get("tarifas", []):
        if t["nombre"] == nombre:
            return t
    raise HTTPException(400, f"El vuelo {vuelo['codigo']} no tiene tarifa {nombre}")


def habitacion(hotel: dict, tipo: str) -> dict:
    for h in hotel.get("habitaciones", []):
        if h["tipo"] == tipo:
            return h
    raise HTTPException(400, f"El hotel {hotel['nombre']} no tiene habitaciones {tipo}")


def habitaciones_para(personas: int, capacidad: int) -> int:
    return ceil(personas / capacidad)


def _salida_del_tour(db: Database, tour: dict, salida_id: ObjectId) -> dict:
    salida = buscar_o_404(db.salidas, {"_id": salida_id}, "Salida")
    if salida["tour_id"] != tour["_id"]:
        raise HTTPException(400, "La salida no pertenece a ese tour")
    return salida


def _futuro(fecha: datetime, ahora: datetime, que: str) -> None:
    if fecha <= ahora:
        raise HTTPException(400, f"{que} ya pasó")


# ───────────────────────────── Ítems de reserva ─────────────────────────────


def _item(tipo, ref_id, detalle, nombre, ciudad, inicio, fin, cantidad, precio) -> dict:
    return {"tipo": tipo, "ref_id": ref_id, "detalle": detalle, "nombre": nombre, "ciudad": ciudad,
            "inicio": inicio, "fin": fin, "cantidad": cantidad, "precio": precio,
            "subtotal": cantidad * precio}


def cotizar_vuelo(db: Database, vuelo_id: ObjectId, tarifa: str, n: int, ahora: datetime):
    v = buscar_o_404(db.vuelos, {"_id": vuelo_id}, "Vuelo")
    _futuro(v["sale"], ahora, f"El vuelo {v['codigo']}")
    t = _tarifa(v, tarifa)
    item = _item("vuelo", v["_id"], {"codigo": v["codigo"], "tarifa": tarifa},
                 f"{v['origen']}-{v['destino']} {v['codigo']}", v["destino"],
                 v["sale"], v["llega"], n, t["precio"])
    return item, [Movimiento("vuelo", v["_id"], n, tarifa=tarifa)]


def cotizar_hotel(db: Database, hotel_id: ObjectId, tipo_hab: str,
                  entrada: datetime, salida: datetime, personas: int, ahora: datetime):
    h = buscar_o_404(db.hoteles, {"_id": hotel_id}, "Hotel")
    if entrada < a_utc(ahora.date()):
        raise HTTPException(400, "La fecha de entrada ya pasó")
    hab = habitacion(h, tipo_hab)
    noches = (salida - entrada).days
    cuartos = habitaciones_para(personas, hab["capacidad"])
    item = _item("hotel", h["_id"], {"tipo_hab": tipo_hab, "noches": noches, "habitaciones": cuartos},
                 f"{h['nombre']} {tipo_hab}", h["ciudad"], entrada, salida,
                 personas, hab["precio_noche"] * noches)
    mov = Movimiento("noches", h["_id"], cuartos, tipo_hab=tipo_hab, entrada=entrada, salida=salida)
    return item, [mov]


def cotizar_tour(db: Database, tour_id: ObjectId, salida_id: ObjectId, n: int, ahora: datetime):
    t = buscar_o_404(db.tours, {"_id": tour_id}, "Tour")
    s = _salida_del_tour(db, t, salida_id)
    _futuro(s["fecha"], ahora, f"La salida del tour {t['nombre']}")
    if not t.get("ciudad"):
        raise HTTPException(400, f"El tour {t['nombre']} no tiene ciudad registrada")
    fin = s["fecha"] + timedelta(hours=t.get("horas") or 0)
    item = _item("tour", t["_id"], {"salida_id": s["_id"]}, t["nombre"], t["ciudad"],
                 s["fecha"], fin, n, s["precio"])
    return item, [Movimiento("salida", s["_id"], n)]


def cotizar_paquete(db: Database, paquete_id: ObjectId, personas: int, ahora: datetime):
    p = buscar_o_404(db.paquetes, {"_id": paquete_id}, "Paquete")
    if "desde" in p and ahora < p["desde"]:
        raise HTTPException(400, "El paquete aún no está a la venta")
    if "hasta" in p and ahora >= p["hasta"] + timedelta(days=1):     # 'hasta' incluye todo ese día
        raise HTTPException(400, "El paquete ya no está a la venta")

    movimientos, inicios, fines = [], [], []
    for c in p["componentes"]:
        d = c["detalle"]
        if c["tipo"] == "vuelo":
            it, mov = cotizar_vuelo(db, c["ref_id"], d["tarifa"], personas, ahora)
        elif c["tipo"] == "hotel":
            it, mov = cotizar_hotel(db, c["ref_id"], d["tipo_hab"], d["entrada"],
                                    d["entrada"] + timedelta(days=d["noches"]), personas, ahora)
        else:
            it, mov = cotizar_tour(db, c["ref_id"], d["salida_id"], personas, ahora)
        movimientos += mov
        inicios.append(it["inicio"])
        fines.append(it["fin"])

    # El precio sale de las COPIAS del paquete (congeladas al crearlo), no del catálogo actual.
    descuento = p.get("descuento", 0)
    precio = round(sum(c["precio"] for c in p["componentes"]) * (1 - descuento / 100))
    item = _item("paquete", p["_id"], {"descuento": descuento}, p["nombre"], p["destino"],
                 min(inicios), max(fines), personas, precio)
    return item, movimientos


# ───────────────────────────── Componentes de paquete ─────────────────────────────


def armar_componente(db: Database, comp) -> tuple[dict, datetime]:
    """Valida el componente, COPIA nombre y precio por persona, y devuelve su fecha de inicio."""
    ref = ObjectId(comp.ref_id)
    if comp.tipo == "vuelo":
        v = buscar_o_404(db.vuelos, {"_id": ref}, "Vuelo")
        t = _tarifa(v, comp.detalle.tarifa)
        return ({"tipo": "vuelo", "ref_id": ref,
                 "detalle": {"codigo": v["codigo"], "tarifa": t["nombre"]},
                 "nombre": f"{v['origen']}-{v['destino']} {v['codigo']}", "precio": t["precio"]},
                v["sale"])
    if comp.tipo == "hotel":
        h = buscar_o_404(db.hoteles, {"_id": ref}, "Hotel")
        hab = habitacion(h, comp.detalle.tipo_hab)
        entrada = a_utc(comp.detalle.entrada)
        return ({"tipo": "hotel", "ref_id": ref,
                 "detalle": {"tipo_hab": hab["tipo"], "noches": comp.detalle.noches, "entrada": entrada},
                 "nombre": f"{h['nombre']} {hab['tipo']}",
                 "precio": hab["precio_noche"] * comp.detalle.noches},
                entrada)
    t = buscar_o_404(db.tours, {"_id": ref}, "Tour")
    s = _salida_del_tour(db, t, ObjectId(comp.detalle.salida_id))
    return ({"tipo": "tour", "ref_id": ref, "detalle": {"salida_id": s["_id"]},
             "nombre": t["nombre"], "precio": s["precio"]},
            s["fecha"])


# ───────────────────────────── Cancelación ─────────────────────────────


def movimientos_de_reserva(db: Database, reserva: dict) -> list[Movimiento]:
    """Reconstruye, desde los ítems guardados, qué inventario hay que devolver."""
    movs: list[Movimiento] = []
    for it in reserva["items"]:
        d, n = it["detalle"], it["cantidad"]
        if it["tipo"] == "vuelo":
            movs.append(Movimiento("vuelo", it["ref_id"], n, tarifa=d["tarifa"]))
        elif it["tipo"] == "hotel":
            movs.append(Movimiento("noches", it["ref_id"], d["habitaciones"], tipo_hab=d["tipo_hab"],
                                   entrada=it["inicio"], salida=it["fin"]))
        elif it["tipo"] == "tour":
            movs.append(Movimiento("salida", d["salida_id"], n))
        else:  # paquete: sus componentes no se editan por API, así que siguen siendo los reservados
            p = db.paquetes.find_one({"_id": it["ref_id"]}) or {"componentes": []}
            for c in p["componentes"]:
                cd = c["detalle"]
                if c["tipo"] == "vuelo":
                    movs.append(Movimiento("vuelo", c["ref_id"], n, tarifa=cd["tarifa"]))
                elif c["tipo"] == "hotel":
                    h = db.hoteles.find_one({"_id": c["ref_id"]})
                    cap = habitacion(h, cd["tipo_hab"])["capacidad"]
                    movs.append(Movimiento("noches", c["ref_id"], habitaciones_para(n, cap),
                                           tipo_hab=cd["tipo_hab"], entrada=cd["entrada"],
                                           salida=cd["entrada"] + timedelta(days=cd["noches"])))
                else:
                    movs.append(Movimiento("salida", cd["salida_id"], n))
    return movs
