from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.database import get_db
from app.schemas import CiudadCreate, CiudadResponse
from app.utils import buscar_o_404

router = APIRouter()


def exigir_ciudad(db: Database, iata: str) -> None:
    """Mongo no valida referencias entre colecciones: se hace aquí."""
    if not db.ciudades.find_one({"iata": iata}, {"_id": 1}):
        raise HTTPException(400, f"La ciudad {iata} no existe")


@router.get("/", response_model=list[CiudadResponse])
def listar_ciudades(db: Database = Depends(get_db)):
    return list(db.ciudades.find().sort("nombre", 1))


@router.get("/{iata}", response_model=CiudadResponse)
def obtener_ciudad(iata: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.ciudades, {"iata": iata.upper()}, "Ciudad")


@router.post("/", response_model=CiudadResponse, status_code=201)
def crear_ciudad(ciudad: CiudadCreate, db: Database = Depends(get_db)):
    r = db.ciudades.insert_one(ciudad.model_dump())       # iata duplicada -> 409 (handler en main)
    return db.ciudades.find_one({"_id": r.inserted_id})
