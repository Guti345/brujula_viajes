"""
app/main.py — Punto de entrada de la API de Brújula Viajes.

Correr desde la carpeta back/:       uvicorn main:app --reload
Documentación interactiva:            http://127.0.0.1:8000/docs
"""
import logging
import traceback
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import (
    BulkWriteError,
    ConnectionFailure,
    DuplicateKeyError,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from app.database import init_db
from app.inventario import SinDisponibilidad
from app.routers import asesores, ciudades, clientes, hoteles, paquetes, reportes, reservas, tours, vuelos

ERROR_INTERNO = {"detail": "Error interno del servidor"}

# El mensaje de una excepción de Mongo puede traer valores de documentos (nombres, correos), y la
# URL real puede traer un documento de identidad: el log solo lleva método, plantilla de ruta y clase.
log = logging.getLogger("brujula")
if not log.handlers:                # si el módulo se recarga, no se duplica el handler
    _salida = logging.StreamHandler()
    _salida.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_salida)
log.setLevel(logging.INFO)
log.propagate = False


def _ruta(request: Request) -> str:
    """Plantilla de la ruta, por ejemplo /reservas/{codigo}. route.path no trae el prefijo del
    include_router; el prefijo de cada router es el nombre de su módulo (ver include_router abajo)."""
    ruta = request.scope.get("route")
    if ruta is None:
        return "ruta desconocida"
    modulo = ruta.endpoint.__module__
    prefijo = "/" + modulo.rpartition(".")[2] if modulo.startswith("app.routers.") else ""
    return f"{prefijo}{ruta.path}"


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
    return JSONResponse(status_code=409, content={"detail": "Ya existe un registro con ese identificador único"})


@app.exception_handler(OperationFailure)
def fallo_mongo(request: Request, e: OperationFailure):
    if e.code == 121:   # DocumentValidationFailure: el validador $jsonSchema rechazó la escritura
        log.error("422 %s %s %s code=%s", request.method, _ruta(request), type(e).__name__, e.code)
        return JSONResponse(status_code=422, content={"detail": "El documento no cumple el esquema de la base"})
    log.error("500 %s %s %s code=%s", request.method, _ruta(request), type(e).__name__, e.code)
    return JSONResponse(status_code=500, content=ERROR_INTERNO)


@app.exception_handler(BulkWriteError)
def fallo_bulk(request: Request, e: BulkWriteError):
    """generar_noches usa ordered=False: parte de las escrituras pudo aplicarse, así que ninguna
    respuesta afirma que no se guardó nada. Ante cualquier duda se responde 500."""
    detalles = e.details or {}
    codigos = [w.get("code") for w in detalles.get("writeErrors") or []]
    concern = len(detalles.get("writeConcernErrors") or [])
    log.error("%s %s %s writeErrors=%s writeConcernErrors=%s", request.method, _ruta(request),
              type(e).__name__, dict(Counter(codigos)), concern)
    if codigos and not concern:
        if set(codigos) == {11000}:
            return JSONResponse(status_code=409, content={"detail": "Conflicto de llave única al escribir en la base"})
        if set(codigos) == {121}:
            return JSONResponse(status_code=422, content={"detail": "El documento no cumple el esquema de la base"})
    return JSONResponse(status_code=500, content=ERROR_INTERNO)


@app.exception_handler(ServerSelectionTimeoutError)
def mongo_caido(_: Request, e: ServerSelectionTimeoutError):
    return JSONResponse(status_code=503, content={"detail": "MongoDB no responde. ¿Está corriendo?"})


@app.exception_handler(ConnectionFailure)
def sin_conexion(request: Request, e: ConnectionFailure):
    log.error("503 %s %s %s", request.method, _ruta(request), type(e).__name__)
    return JSONResponse(status_code=503, content={"detail": "No hay conexión con la base de datos"})


# ─────────────── Errores del servidor -> 500 sin detalles internos ───────────────
@app.exception_handler(ResponseValidationError)
def respuesta_invalida(request: Request, e: ResponseValidationError):
    """Un documento de Mongo no cumple el response_model: el problema es del servidor, no del cliente.
    Solo se registra el tipo de cada error: input, ctx y loc pueden traer valores del documento."""
    errores = e.errors()
    log.error("500 %s %s %s errores=%s tipos=%s", request.method, _ruta(request), type(e).__name__,
              len(errores), [x["type"] for x in errores])
    return JSONResponse(status_code=500, content=ERROR_INTERNO)


@app.exception_handler(Exception)
def error_inesperado(request: Request, e: Exception):
    frames = [f"{f.filename}:{f.lineno} {f.name}" for f in traceback.extract_tb(e.__traceback__)]
    log.error("500 %s %s %s frames=%s", request.method, _ruta(request), type(e).__name__, frames)
    return JSONResponse(status_code=500, content=ERROR_INTERNO)


@app.get("/", tags=["General"])
def raiz():
    return {"message": "Bienvenido a Brújula Viajes API", "docs": "/docs", "status": "online"}
