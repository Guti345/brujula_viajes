from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.database import get_db
from app.routers.ciudades import exigir_ciudad
from app.schemas import VueloCreate, VueloResponse
from app.utils import BOGOTA, buscar_o_404, oid_o_404

router = APIRouter()


@router.get("/", response_model=list[VueloResponse])
def buscar_vuelos(
    origen: str | None = None,
    destino: str | None = None,
    fecha: date | None = Query(None, description="Día de salida en hora de Bogotá"),
    limite: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
):
    """Usa el índice {origen, destino, sale}: filtros de igualdad primero, rango al final."""
    filtro: dict = {}
    if origen:
        filtro["origen"] = origen.upper()
    if destino:
        filtro["destino"] = destino.upper()
    if fecha:
        inicio = datetime(fecha.year, fecha.month, fecha.day, tzinfo=BOGOTA)
        filtro["sale"] = {"$gte": inicio, "$lt": inicio + timedelta(days=1)}
    return list(db.vuelos.find(filtro).sort("sale", 1).limit(limite))


@router.get("/{vuelo_id}", response_model=VueloResponse)
def obtener_vuelo(vuelo_id: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.vuelos, {"_id": oid_o_404(vuelo_id, "Vuelo")}, "Vuelo")


@router.post("/", response_model=VueloResponse, status_code=201)
def crear_vuelo(vuelo: VueloCreate, db: Database = Depends(get_db)):
    exigir_ciudad(db, vuelo.origen)
    exigir_ciudad(db, vuelo.destino)
    doc = vuelo.model_dump()
    for t in doc["tarifas"]:
        t["libres"] = t["sillas"]          # el inventario nace lleno
    r = db.vuelos.insert_one(doc)
    return db.vuelos.find_one({"_id": r.inserted_id})
