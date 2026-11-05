"""
app/inventario.py — Descuento y devolución de inventario SIN sobreventa (decisión 1b: compensación).

Idea central: cada descuento es UNA escritura condicional sobre UN documento:
    filtro  { ..., libres >= n }   +   update  { $inc: { libres: -n } }
Mongo evalúa filtro y $inc de forma atómica por documento, así que dos clientes nunca pueden
tomar la misma última silla/habitación/cupo. Si una operación de una reserva falla, se
devuelve (con $inc positivo) todo lo que ya se había descontado: eso es la compensación.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from bson import ObjectId
from pymongo.database import Database

from .utils import rango_noches

log = logging.getLogger("brujula.inventario")


class SinDisponibilidad(Exception):
    """No hay inventario suficiente; el mensaje dice exactamente qué faltó."""


# ─────────────────────────── Movimientos ───────────────────────────
@dataclass
class Movimiento:
    """Una unidad de inventario a descontar (o devolver)."""
    tipo: str                         # "vuelo" | "noches" | "salida"
    ref_id: ObjectId
    n: int                            # sillas, habitaciones o cupos
    tarifa: str | None = None         # vuelo
    tipo_hab: str | None = None       # noches
    entrada: datetime | None = None   # noches
    salida: datetime | None = None    # noches
    hechas: list = field(default_factory=list)   # noches ya descontadas (para revertir solo esas)


def _descontar_vuelo(db: Database, m: Movimiento) -> None:
    r = db.vuelos.update_one(
        {"_id": m.ref_id, "tarifas": {"$elemMatch": {"nombre": m.tarifa, "libres": {"$gte": m.n}}}},
        {"$inc": {"tarifas.$.libres": -m.n}},      # $ = la tarifa que cumplió el $elemMatch
    )
    if r.matched_count == 0:
        raise SinDisponibilidad(f"Vuelo sin {m.n} sillas libres en tarifa {m.tarifa}")


def _devolver_vuelo(db: Database, m: Movimiento) -> None:
    db.vuelos.update_one({"_id": m.ref_id, "tarifas.nombre": m.tarifa},
                         {"$inc": {"tarifas.$.libres": m.n}})


def _descontar_noches(db: Database, m: Movimiento) -> None:
    for fecha in rango_noches(m.entrada, m.salida):
        r = db.noches.update_one(
            {"hotel_id": m.ref_id, "tipo": m.tipo_hab, "fecha": fecha, "libres": {"$gte": m.n}},
            {"$inc": {"libres": -m.n}},
        )
        if r.matched_count == 0:   # sin cupo O noche no generada: ambas se reportan igual
            _devolver_noches(db, m)            # compensa las noches de ESTE ítem ya descontadas
            raise SinDisponibilidad(
                f"Sin {m.n} habitación(es) {m.tipo_hab} la noche del {fecha.date().isoformat()}"
            )
        m.hechas.append(fecha)


def _devolver_noches(db: Database, m: Movimiento) -> None:
    for fecha in m.hechas:
        db.noches.update_one({"hotel_id": m.ref_id, "tipo": m.tipo_hab, "fecha": fecha},
                             {"$inc": {"libres": m.n}})
    m.hechas.clear()


def _descontar_salida(db: Database, m: Movimiento) -> None:
    r = db.salidas.update_one({"_id": m.ref_id, "libres": {"$gte": m.n}}, {"$inc": {"libres": -m.n}})
    if r.matched_count == 0:
        raise SinDisponibilidad(f"La salida del tour no tiene {m.n} cupos libres")


def _devolver_salida(db: Database, m: Movimiento) -> None:
    db.salidas.update_one({"_id": m.ref_id}, {"$inc": {"libres": m.n}})


_DESCONTAR = {"vuelo": _descontar_vuelo, "noches": _descontar_noches, "salida": _descontar_salida}
_DEVOLVER = {"vuelo": _devolver_vuelo, "noches": _devolver_noches, "salida": _devolver_salida}


# ─────────────────────────── API del módulo ───────────────────────────
def descontar_todo(db: Database, movimientos: list[Movimiento]) -> list[Movimiento]:
    """Descuenta en orden. Si uno falla, revierte los anteriores y relanza el error."""
    hechos: list[Movimiento] = []
    try:
        for m in movimientos:
            _DESCONTAR[m.tipo](db, m)
            hechos.append(m)
    except Exception:
        devolver_todo(db, hechos)
        raise
    return hechos


def devolver_todo(db: Database, movimientos: list[Movimiento]) -> None:
    """Devuelve inventario. Usado en la compensación y al cancelar una reserva."""
    for m in reversed(movimientos):
        if m.tipo == "noches" and not m.hechas:     # al cancelar: todas las noches del rango
            m.hechas = rango_noches(m.entrada, m.salida)
        try:
            _DEVOLVER[m.tipo](db, m)
        except Exception as e:                      # no se detiene: registra para revisión manual
            log.error("No se pudo devolver inventario tipo=%s error=%s", m.tipo, type(e).__name__)
