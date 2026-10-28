from fastapi import APIRouter, Depends, HTTPException
from pymongo import ReturnDocument
from pymongo.database import Database
from typing import List

from app.database import get_db, siguiente_id, a_documento, referencias_inexistentes
from app.models import PERSONAL_MEDICO
from app.schemas import PersonalMedicoCreate, PersonalMedicoResponse

router = APIRouter()

SIN_ID_MONGO = {"_id": 0}


def validar_jefe(datos: PersonalMedicoCreate):
    if referencias_inexistentes(datos.model_dump(), {"jefe_id": PERSONAL_MEDICO}):
        raise HTTPException(status_code=400, detail="El jefe indicado no existe")


@router.get("/", response_model=List[PersonalMedicoResponse])
def listar_personal(db: Database = Depends(get_db)):
    return list(db[PERSONAL_MEDICO].find({}, SIN_ID_MONGO))


@router.get("/{personal_id}", response_model=PersonalMedicoResponse)
def obtener_personal(personal_id: int, db: Database = Depends(get_db)):
    personal = db[PERSONAL_MEDICO].find_one({"id": personal_id}, SIN_ID_MONGO)
    if not personal:
        raise HTTPException(status_code=404, detail="Personal médico no encontrado")
    return personal


@router.post("/", response_model=PersonalMedicoResponse, status_code=201)
def crear_personal(personal: PersonalMedicoCreate, db: Database = Depends(get_db)):
    validar_jefe(personal)
    # mode="json" convierte el Enum TipoPersonalMedico a su valor de texto
    nuevo = {"id": siguiente_id(PERSONAL_MEDICO), **a_documento(personal.model_dump(mode="json"))}
    db[PERSONAL_MEDICO].insert_one(nuevo)
    nuevo.pop("_id")
    return nuevo


@router.put("/{personal_id}", response_model=PersonalMedicoResponse)
def actualizar_personal(personal_id: int, datos: PersonalMedicoCreate, db: Database = Depends(get_db)):
    validar_jefe(datos)
    personal = db[PERSONAL_MEDICO].find_one_and_update(
        {"id": personal_id},
        {"$set": a_documento(datos.model_dump(mode="json"))},
        projection=SIN_ID_MONGO,
        return_document=ReturnDocument.AFTER,
    )
    if not personal:
        raise HTTPException(status_code=404, detail="Personal médico no encontrado")
    return personal


@router.delete("/{personal_id}", status_code=204)
def eliminar_personal(personal_id: int, db: Database = Depends(get_db)):
    resultado = db[PERSONAL_MEDICO].delete_one({"id": personal_id})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Personal médico no encontrado")
