from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database import get_db
from app.schemas import ClienteCreate, ClienteResponse, ClienteUpdate
from app.utils import buscar_o_404

router = APIRouter()


@router.get("/", response_model=list[ClienteResponse])
def listar_clientes(db: Database = Depends(get_db)):
    return list(db.clientes.find().sort("nombre", 1))


@router.get("/{documento}", response_model=ClienteResponse)
def obtener_cliente(documento: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.clientes, {"documento": documento}, "Cliente")     # índice único


@router.post("/", response_model=ClienteResponse, status_code=201)
def crear_cliente(cliente: ClienteCreate, db: Database = Depends(get_db)):
    r = db.clientes.insert_one(cliente.model_dump(exclude_none=True))       # documento repetido -> 409
    return db.clientes.find_one({"_id": r.inserted_id})


@router.patch("/{documento}", response_model=ClienteResponse)
def actualizar_cliente(documento: str, datos: ClienteUpdate, db: Database = Depends(get_db)):
    """Cambiar el nombre aquí NO cambia las reservas viejas: allá quedó la copia (snapshot)."""
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        db.clientes.update_one({"documento": documento}, {"$set": cambios})
    return buscar_o_404(db.clientes, {"documento": documento}, "Cliente")
