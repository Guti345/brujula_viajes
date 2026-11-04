from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.cotizacion import armar_componente
from app.database import get_db
from app.routers.ciudades import exigir_ciudad
from app.schemas import PaqueteCreate, PaqueteResponse
from app.utils import a_utc, ahora, buscar_o_404, oid_o_404

router = APIRouter()


@router.get("/", response_model=list[PaqueteResponse])
def listar_paquetes(destino: str | None = None, solo_vigentes: bool = True,
                    db: Database = Depends(get_db)):
    """Usa el índice {destino, hasta}."""
    filtro: dict = {}
    if destino:
        filtro["destino"] = destino.upper()
    if solo_vigentes:
        hoy = a_utc(ahora().date())
        filtro["hasta"] = {"$gte": hoy}
        filtro["desde"] = {"$lte": hoy}
    return list(db.paquetes.find(filtro).sort("hasta", 1))


@router.get("/{paquete_id}", response_model=PaqueteResponse)
def obtener_paquete(paquete_id: str, db: Database = Depends(get_db)):
    return buscar_o_404(db.paquetes, {"_id": oid_o_404(paquete_id, "Paquete")}, "Paquete")


@router.post("/", response_model=PaqueteResponse, status_code=201)
def crear_paquete(paquete: PaqueteCreate, db: Database = Depends(get_db)):
    """REF + COPIA: guarda ref_id y copia nombre y precio por persona de cada componente.
    Los componentes no se pueden editar después (la cancelación depende de ellos)."""
    exigir_ciudad(db, paquete.destino)
    componentes, fechas = [], []
    for c in paquete.componentes:
        comp, fecha = armar_componente(db, c)
        componentes.append(comp)
        fechas.append(fecha)

    desde, hasta = a_utc(paquete.desde), a_utc(paquete.hasta)
    if hasta + timedelta(days=1) > min(fechas):               # decisión punto 4
        raise HTTPException(400, "La venta debe cerrar (hasta) a más tardar el día anterior al viaje")

    doc = {"nombre": paquete.nombre, "destino": paquete.destino, "descuento": paquete.descuento,
           "desde": desde, "hasta": hasta, "componentes": componentes}
    r = db.paquetes.insert_one(doc)
    return db.paquetes.find_one({"_id": r.inserted_id})
