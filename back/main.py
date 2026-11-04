"""
app/main.py — Punto de entrada de la API de Brújula Viajes.

Correr desde la carpeta back/:       uvicorn main:app --reload
Documentación interactiva:            http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, OperationFailure, ServerSelectionTimeoutError

from app.database import init_db
from app.inventario import SinDisponibilidad
from app.routers import asesores, ciudades, clientes, hoteles, paquetes, reportes, reservas, tours, vuelos


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()            # equivalente a Base.metadata.create_all(): validadores + índices
    yield


app = FastAPI(
    title="Brújula Viajes API",
    description="Agencia de viajes: vuelos, hoteles por noche, tours, paquetes y reservas sin sobreventa",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ciudades.router, prefix="/ciudades", tags=["Ciudades"])
app.include_router(vuelos.router, prefix="/vuelos", tags=["Vuelos"])
app.include_router(hoteles.router, prefix="/hoteles", tags=["Hoteles"])
app.include_router(tours.router, prefix="/tours", tags=["Tours"])
app.include_router(paquetes.router, prefix="/paquetes", tags=["Paquetes"])
app.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
app.include_router(asesores.router, prefix="/asesores", tags=["Asesores"])
app.include_router(reservas.router, prefix="/reservas", tags=["Reservas"])
app.include_router(reportes.router, prefix="/reportes", tags=["Reportes"])


# ─────────────── Errores de Mongo -> respuestas HTTP claras ───────────────
@app.exception_handler(SinDisponibilidad)
def sin_disponibilidad(_: Request, e: SinDisponibilidad):
    return JSONResponse(status_code=409, content={"detail": str(e)})


@app.exception_handler(DuplicateKeyError)
def duplicado(_: Request, e: DuplicateKeyError):
    clave = (e.details or {}).get("keyValue", {})
    return JSONResponse(status_code=409, content={"detail": f"Ya existe un registro con {clave}"})


@app.exception_handler(OperationFailure)
def fallo_mongo(_: Request, e: OperationFailure):
    if e.code == 121:   # DocumentValidationFailure: el validador $jsonSchema rechazó la escritura
        return JSONResponse(status_code=422, content={"detail": "El documento no cumple el esquema de la base",
                                  "mongo": (e.details or {}).get("errInfo")})
    return JSONResponse(status_code=500, content={"detail": f"Error de MongoDB: {e}"})


@app.exception_handler(ServerSelectionTimeoutError)
def mongo_caido(_: Request, e: ServerSelectionTimeoutError):
    return JSONResponse(status_code=503, content={"detail": "MongoDB no responde. ¿Está corriendo?"})


@app.get("/", tags=["General"])
def raiz():
    return {"message": "Bienvenido a Brújula Viajes API", "docs": "/docs", "status": "online"}
