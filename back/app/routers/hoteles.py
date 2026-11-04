from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import UpdateOne
from pymongo.database import Database

from app.cotizacion import habitacion, habitaciones_para
from app.database import get_db
from app.routers.ciudades import exigir_ciudad
from app.schemas import (
    DisponibilidadResponse,
    HotelCreate,
    HotelResponse,
    HotelUpdate,
    NocheResponse,
    NochesGenerar,
    NochesGeneradas,
    TipoHab,
)
from app.utils import a_mongo, a_utc, buscar_o_404, oid_o_404, rango_noches

router = APIRouter()


@router.get("/", response_model=list[HotelResponse])
def listar_hoteles(ciudad: str | None = None, db: Database = Depends(get_db)):
    filtro = {"ciudad": ciudad.upper()} if ciudad else {}
    return list(db.hoteles.find(filtro).sort("nombre", 1))


@router.get("/cerca", response_model=list[HotelResponse])
def hoteles_cerca(lon: float = Query(..., ge=-180, le=180), lat: float = Query(..., ge=-90, le=90),
                  km: float = Query(5, gt=0, le=100), db: Database = Depends(get_db)):
    """Usa el índice 2dsphere de `ubicacion`; resultados ordenados del más cercano al más lejano."""
    return list(db.hoteles.find({"ubicacion": {"$nearSphere": {
        "$geometry": {"type": "Point", "coordinates": [lon, lat]}, "$maxDistance": km * 1000}}}))


@router.get("/{hotel_id}", response_model=HotelResponse)
def obtener_hotel(hotel_id: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.hoteles, {"_id": oid_o_404(hotel_id, "Hotel")}, "Hotel")


@router.post("/", response_model=HotelResponse, status_code=201)
def crear_hotel(hotel: HotelCreate, db: Database = Depends(get_db)):
    exigir_ciudad(db, hotel.ciudad)
    r = db.hoteles.insert_one(hotel.model_dump(exclude_none=True))
    return db.hoteles.find_one({"_id": r.inserted_id})


@router.patch("/{hotel_id}", response_model=HotelResponse)
def actualizar_hotel(hotel_id: str, datos: HotelUpdate, db: Database = Depends(get_db)):
    _id = oid_o_404(hotel_id, "Hotel")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        db.hoteles.update_one({"_id": _id}, {"$set": cambios})
    return buscar_o_404(db.hoteles, {"_id": _id}, "Hotel")


# ─────────────────────────── Noches (punto 6) ───────────────────────────
@router.post("/{hotel_id}/noches", response_model=NochesGeneradas, status_code=201)
def generar_noches(hotel_id: str, datos: NochesGenerar, db: Database = Depends(get_db)):
    """Crea una noche por tipo y fecha con libres = cantidad. Las que ya existen NO se tocan
    ($setOnInsert + upsert), así que volver a generar nunca pisa lo ya vendido."""
    h = buscar_o_404(db.hoteles, {"_id": oid_o_404(hotel_id, "Hotel")}, "Hotel")
    tipos = datos.tipos or [x["tipo"] for x in h.get("habitaciones", [])]
    ops = []
    for tipo in tipos:
        cantidad = habitacion(h, tipo)["cantidad"]
        for fecha in rango_noches(a_utc(datos.desde), a_utc(datos.hasta)):
            ops.append(UpdateOne({"hotel_id": h["_id"], "tipo": tipo, "fecha": fecha},
                                 {"$setOnInsert": {"libres": cantidad}}, upsert=True))
    if not ops:
        raise HTTPException(409, "El hotel no tiene habitaciones registradas")
    r = db.noches.bulk_write(ops, ordered=False)          # un solo viaje a la base
    return {"creadas": r.upserted_count, "existentes": len(ops) - r.upserted_count}


@router.get("/{hotel_id}/noches", response_model=list[NocheResponse])
def listar_noches(hotel_id: str, desde: date, hasta: date, tipo: TipoHab | None = None,
                  db: Database = Depends(get_db)):
    filtro = a_mongo({"hotel_id": oid_o_404(hotel_id, "Hotel"),
                      "fecha": {"$gte": desde, "$lt": hasta}})
    if tipo:
        filtro["tipo"] = tipo
    return list(db.noches.find(filtro).sort([("tipo", 1), ("fecha", 1)]))


@router.get("/{hotel_id}/disponibilidad", response_model=DisponibilidadResponse)
def disponibilidad(hotel_id: str, tipo: TipoHab, entrada: date, salida: date,
                   personas: int = Query(1, ge=1), db: Database = Depends(get_db)):
    """'Verificar' del modelo: todas las noches de [entrada, salida) deben tener libres >= n."""
    if salida <= entrada:
        raise HTTPException(422, "salida debe ser posterior a entrada")
    h = buscar_o_404(db.hoteles, {"_id": oid_o_404(hotel_id, "Hotel")}, "Hotel")
    n = habitaciones_para(personas, habitacion(h, tipo)["capacidad"])
    noches = rango_noches(a_utc(entrada), a_utc(salida))
    con_cupo = {d["fecha"] for d in db.noches.find(
        {"hotel_id": h["_id"], "tipo": tipo, "fecha": {"$in": noches}, "libres": {"$gte": n}},
        {"fecha": 1})}
    faltan = [f.date() for f in noches if f not in con_cupo]
    return {"hotel_id": str(h["_id"]), "tipo": tipo, "personas": personas, "habitaciones": n,
            "noches": len(noches), "disponible": not faltan, "faltan": faltan}
