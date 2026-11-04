"""app/utils.py — Utilidades compartidas por los routers (fechas, ObjectId, errores)."""
from datetime import date, datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException

UTC = timezone.utc
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")   # Colombia no tiene horario de verano


def oid(valor: str) -> ObjectId:
    """El DTO ya validó el formato; aquí solo se convierte texto -> ObjectId."""
    return ObjectId(valor)


def oid_o_404(valor: str, que: str) -> ObjectId:
    """Para ids que llegan en la URL (no pasan por un DTO)."""
    if not ObjectId.is_valid(valor):
        raise HTTPException(404, f"{que} no encontrado")
    return ObjectId(valor)


def a_utc(d: date) -> datetime:
    """Fecha de día -> 00:00 UTC (punto 8: así se guardan noches, entradas y vigencias)."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def ahora() -> datetime:
    """Hora actual en UTC, truncada a milisegundos (precisión de BSON)."""
    t = datetime.now(UTC)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


def rango_noches(entrada: datetime, salida: datetime) -> list[datetime]:
    """Noches del intervalo [entrada, salida)."""
    return [entrada + timedelta(days=i) for i in range((salida - entrada).days)]


def buscar_o_404(coleccion, filtro: dict, que: str) -> dict:
    doc = coleccion.find_one(filtro)
    if doc is None:
        raise HTTPException(404, f"{que} no encontrado")
    return doc


def a_mongo(datos: dict) -> dict:
    """Convierte recursivamente `date` -> datetime UTC, porque BSON no tiene tipo solo-fecha."""
    if isinstance(datos, dict):
        return {k: a_mongo(v) for k, v in datos.items()}
    if isinstance(datos, list):
        return [a_mongo(v) for v in datos]
    if isinstance(datos, date) and not isinstance(datos, datetime):
        return a_utc(datos)
    return datos
