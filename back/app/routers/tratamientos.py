from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument
from pymongo.database import Database
from typing import List

from app.database import get_db, siguiente_id, a_documento, referencias_inexistentes
from app.models import TRATAMIENTOS, PACIENTES, PERSONAL_MEDICO
from app.schemas import TratamientoCreate, TratamientoResponse, TratamientoDetalleResponse

router = APIRouter()

SIN_ID_MONGO = {"_id": 0}


def validar_referencias(datos: TratamientoCreate):
    # Reemplaza las ForeignKey de SQL: Mongo aceptaría cualquier id sin quejarse
    faltantes = referencias_inexistentes(
        datos.model_dump(),
        {"paciente_id": PACIENTES, "medico_id": PERSONAL_MEDICO},
    )
    if "paciente_id" in faltantes:
        raise HTTPException(status_code=400, detail="El paciente indicado no existe")
    if "medico_id" in faltantes:
        raise HTTPException(status_code=400, detail="El médico indicado no existe")


@router.get("/", response_model=List[TratamientoResponse])
def listar_tratamientos(db: Database = Depends(get_db)):
    return list(db[TRATAMIENTOS].find({}, SIN_ID_MONGO))


@router.get("/{tratamiento_id}/detalle", response_model=TratamientoDetalleResponse)
def obtener_tratamiento_detalle(tratamiento_id: int, db: Database = Depends(get_db)):
    # Equivalente en SQL:
    #   SELECT * FROM tratamientos t
    #   LEFT JOIN pacientes p ON p.id = t.paciente_id
    #   LEFT JOIN personal_medico m ON m.id = t.medico_id
    #   WHERE t.id = :tratamiento_id
    pipeline = [
        {"$match": {"id": tratamiento_id}},
        {"$lookup": {"from": PACIENTES, "localField": "paciente_id", "foreignField": "id", "as": "paciente"}},
        {"$lookup": {"from": PERSONAL_MEDICO, "localField": "medico_id", "foreignField": "id", "as": "medico"}},
        # $lookup siempre devuelve un arreglo; $unwind lo convierte en un solo objeto
        {"$unwind": {"path": "$paciente", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$medico", "preserveNullAndEmptyArrays": True}},
        {"$project": {"_id": 0, "paciente._id": 0, "medico._id": 0}},
    ]
    tratamiento = next(db[TRATAMIENTOS].aggregate(pipeline), None)
    if not tratamiento:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado")
    return tratamiento


@router.get("/{tratamiento_id}", response_model=TratamientoResponse)
def obtener_tratamiento(tratamiento_id: int, db: Database = Depends(get_db)):
    tratamiento = db[TRATAMIENTOS].find_one({"id": tratamiento_id}, SIN_ID_MONGO)
    if not tratamiento:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado")
    return tratamiento


@router.post("/", response_model=TratamientoResponse, status_code=201)
def crear_tratamiento(tratamiento: TratamientoCreate, db: Database = Depends(get_db)):
    validar_referencias(tratamiento)
    # Los valores por defecto que antes ponía SQLAlchemy (default="Activo") ahora se ponen aquí
    nuevo = {
        "id": siguiente_id(TRATAMIENTOS),
        **a_documento(tratamiento.model_dump()),
        "estado": "Activo",
        "eficacia_calculada": None,
    }
    db[TRATAMIENTOS].insert_one(nuevo)
    nuevo.pop("_id")
    return nuevo


@router.put("/{tratamiento_id}", response_model=TratamientoResponse)
def actualizar_tratamiento(tratamiento_id: int, datos: TratamientoCreate, db: Database = Depends(get_db)):
    validar_referencias(datos)
    tratamiento = db[TRATAMIENTOS].find_one_and_update(
        {"id": tratamiento_id},
        {"$set": a_documento(datos.model_dump())},
        projection=SIN_ID_MONGO,
        return_document=ReturnDocument.AFTER,
    )
    if not tratamiento:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado")
    return tratamiento


@router.delete("/{tratamiento_id}", status_code=204)
def eliminar_tratamiento(tratamiento_id: int, db: Database = Depends(get_db)):
    resultado = db[TRATAMIENTOS].delete_one({"id": tratamiento_id})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tratamiento no encontrado")
