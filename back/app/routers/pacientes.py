from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument
from pymongo.database import Database
from typing import List

from app.database import get_db, siguiente_id, a_documento, referencias_inexistentes
from app.models import PACIENTES
from app.schemas import PacienteCreate, PacienteResponse

router = APIRouter()

# Proyección para no devolver el _id (ObjectId) de Mongo, que no es serializable a JSON
SIN_ID_MONGO = {"_id": 0}


def validar_referido(datos: PacienteCreate):
    # referido_por_id apunta a la misma colección (auto-referencia), se valida con $lookup
    if referencias_inexistentes(datos.model_dump(), {"referido_por_id": PACIENTES}):
        raise HTTPException(status_code=400, detail="El paciente que refiere no existe")


@router.get("/", response_model=List[PacienteResponse])
def listar_pacientes(db: Database = Depends(get_db)):
    return list(db[PACIENTES].find({}, SIN_ID_MONGO))


@router.get("/{paciente_id}", response_model=PacienteResponse)
def obtener_paciente(paciente_id: int, db: Database = Depends(get_db)):
    paciente = db[PACIENTES].find_one({"id": paciente_id}, SIN_ID_MONGO)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return paciente


@router.post("/", response_model=PacienteResponse, status_code=201)
def crear_paciente(paciente: PacienteCreate, db: Database = Depends(get_db)):
    validar_referido(paciente)
    nuevo = {"id": siguiente_id(PACIENTES), **a_documento(paciente.model_dump())}
    db[PACIENTES].insert_one(nuevo)
    nuevo.pop("_id")  # insert_one agrega el _id al diccionario
    return nuevo


@router.put("/{paciente_id}", response_model=PacienteResponse)
def actualizar_paciente(paciente_id: int, datos: PacienteCreate, db: Database = Depends(get_db)):
    validar_referido(datos)
    paciente = db[PACIENTES].find_one_and_update(
        {"id": paciente_id},
        {"$set": a_documento(datos.model_dump())},
        projection=SIN_ID_MONGO,
        return_document=ReturnDocument.AFTER,
    )
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return paciente


@router.delete("/{paciente_id}", status_code=204)
def eliminar_paciente(paciente_id: int, db: Database = Depends(get_db)):
    resultado = db[PACIENTES].delete_one({"id": paciente_id})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
