from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.database import get_db
from app.schemas import ClienteCreate, ClienteResponse, ClienteUpdate, TipoDocumento, validar_documento
from app.utils import buscar_o_404

router = APIRouter()

TIPO = Query(None, description="Tipo de documento; necesario si dos tipos comparten el número")


def _uno(db: Database, documento: str, tipo: str | None) -> dict:
    """El cliente de ese documento (y tipo, si viene). Sin tipo y con varias coincidencias no se
    escoge uno al azar: 409 para que indiquen el tipo."""
    filtro = {"documento": documento}
    if tipo:
        filtro["tipo"] = tipo                                   # índice único (tipo, documento)
    if db.clientes.count_documents(filtro, limit=2) > 1:
        raise HTTPException(409, "Hay más de un cliente con ese documento; indica el tipo")
    return buscar_o_404(db.clientes, filtro, "Cliente")


@router.get("/", response_model=list[ClienteResponse])
def listar_clientes(db: Database = Depends(get_db)):
    return list(db.clientes.find().sort("nombre", 1))


@router.get("/{documento}", response_model=ClienteResponse)
def obtener_cliente(documento: str, tipo: TipoDocumento | None = TIPO, db: Database = Depends(get_db)):
    return _uno(db, documento, tipo)


@router.post("/", response_model=ClienteResponse, status_code=201)
def crear_cliente(cliente: ClienteCreate, db: Database = Depends(get_db)):
    # exclude_none: sin tipo, el campo no se guarda (el validador de la base no acepta tipo null)
    r = db.clientes.insert_one(cliente.model_dump(exclude_none=True))   # par (tipo, documento) repetido -> 409
    return db.clientes.find_one({"_id": r.inserted_id})


@router.patch("/{documento}", response_model=ClienteResponse)
def actualizar_cliente(documento: str, datos: ClienteUpdate, tipo: TipoDocumento | None = TIPO,
                       db: Database = Depends(get_db)):
    """Cambiar el nombre aquí NO cambia las reservas viejas: allá quedó la copia (snapshot)."""
    cliente = _uno(db, documento, tipo)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("tipo", "") is None:
        del cambios["tipo"]                     # un tipo null nunca se guarda ni borra el que había
    if "tipo" in cambios:
        # Clasificar: el par final (tipo nuevo + documento del registro) debe cumplir la regla del tipo
        error = validar_documento(cambios["tipo"], cliente["documento"])
        if error:
            raise HTTPException(422, error)
    if cambios:
        db.clientes.update_one({"_id": cliente["_id"]}, {"$set": cambios})   # nuevo par repetido -> 409
    return buscar_o_404(db.clientes, {"_id": cliente["_id"]}, "Cliente")
