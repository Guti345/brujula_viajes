from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.database import get_db
from app.routers.ciudades import exigir_ciudad
from app.schemas import SalidaCreate, SalidaResponse, TourCreate, TourResponse, TourUpdate
from app.utils import ahora, buscar_o_404, oid_o_404

router = APIRouter()


@router.get("/", response_model=list[TourResponse])
def listar_tours(ciudad: str | None = None, db: Database = Depends(get_db)):
    filtro = {"ciudad": ciudad.upper()} if ciudad else {}
    return list(db.tours.find(filtro).sort("nombre", 1))


@router.get("/{tour_id}", response_model=TourResponse)
def obtener_tour(tour_id: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.tours, {"_id": oid_o_404(tour_id, "Tour")}, "Tour")


@router.post("/", response_model=TourResponse, status_code=201)
def crear_tour(tour: TourCreate, db: Database = Depends(get_db)):
    if tour.ciudad:
        exigir_ciudad(db, tour.ciudad)
    r = db.tours.insert_one(tour.model_dump(exclude_none=True))
    return db.tours.find_one({"_id": r.inserted_id})


@router.patch("/{tour_id}", response_model=TourResponse)
def actualizar_tour(tour_id: str, datos: TourUpdate, db: Database = Depends(get_db)):
    _id = oid_o_404(tour_id, "Tour")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        db.tours.update_one({"_id": _id}, {"$set": cambios})
    return buscar_o_404(db.tours, {"_id": _id}, "Tour")


# ─────────────────────────── Salidas ───────────────────────────
@router.get("/{tour_id}/salidas", response_model=list[SalidaResponse])
def listar_salidas(tour_id: str, solo_futuras: bool = True, db: Database = Depends(get_db)):
    filtro: dict = {"tour_id": oid_o_404(tour_id, "Tour")}
    if solo_futuras:
        filtro["fecha"] = {"$gt": ahora()}
    return list(db.salidas.find(filtro).sort("fecha", 1))     # índice {tour_id, fecha}


@router.post("/{tour_id}/salidas", response_model=SalidaResponse, status_code=201)
def crear_salida(tour_id: str, salida: SalidaCreate, db: Database = Depends(get_db)):
    t = buscar_o_404(db.tours, {"_id": oid_o_404(tour_id, "Tour")}, "Tour")
    if salida.tour_id != str(t["_id"]):
        raise HTTPException(400, "tour_id del cuerpo no coincide con el de la URL")
    doc = salida.model_dump()
    doc.update(tour_id=t["_id"], libres=salida.cupos)          # inventario nace lleno
    r = db.salidas.insert_one(doc)                             # misma fecha -> 409
    return db.salidas.find_one({"_id": r.inserted_id})
