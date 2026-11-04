from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.database import get_db
from app.schemas import AsesorCreate, AsesorResponse, AsesorUpdate
from app.utils import buscar_o_404

router = APIRouter()


def asesor_activo(db: Database, codigo: str) -> dict:
    """historial.usuario guarda asesores.codigo (punto 9); solo un asesor activo puede operar."""
    a = db.asesores.find_one({"codigo": codigo})
    if not a:
        raise HTTPException(404, f"El asesor {codigo} no existe")
    if not a.get("activo", True):
        raise HTTPException(409, f"El asesor {codigo} está inactivo")
    return a


@router.get("/", response_model=list[AsesorResponse])
def listar_asesores(db: Database = Depends(get_db)):
    return list(db.asesores.find().sort("codigo", 1))


@router.get("/{codigo}", response_model=AsesorResponse)
def obtener_asesor(codigo: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.asesores, {"codigo": codigo}, "Asesor")


@router.post("/", response_model=AsesorResponse, status_code=201)
def crear_asesor(asesor: AsesorCreate, db: Database = Depends(get_db)):
    r = db.asesores.insert_one(asesor.model_dump())
    return db.asesores.find_one({"_id": r.inserted_id})


@router.patch("/{codigo}", response_model=AsesorResponse)
def actualizar_asesor(codigo: str, datos: AsesorUpdate, db: Database = Depends(get_db)):
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        db.asesores.update_one({"codigo": codigo}, {"$set": cambios})
    return buscar_o_404(db.asesores, {"codigo": codigo}, "Asesor")
