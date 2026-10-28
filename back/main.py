from fastapi import FastAPI
from app.database import crear_indices
from app.routers import pacientes, tratamientos, personal

# 1. Preparar la base de datos
# En MongoDB no hay que crear tablas: las colecciones (y la base de datos)
# se crean solas con el primer documento insertado. Solo creamos los índices
# únicos sobre el campo "id" para que no haya ids repetidos.
crear_indices()

# 2. Instancia principal de la API
app = FastAPI(
    title="OrthoConnect API",
    description="Sistema de gestión para clínica odontológica con arquitectura desacoplada",
    version="1.0.0"
)

# 3. Incluir los Routers (Controladores)
# Esto mantiene el main.py limpio y delega la lógica a cada archivo en /routers
app.include_router(pacientes.router, prefix="/pacientes", tags=["Pacientes"])
app.include_router(tratamientos.router, prefix="/tratamientos", tags=["Tratamientos"])
app.include_router(personal.router, prefix="/personal", tags=["Personal Médico"])

# 4. Ruta de bienvenida (Root)
@app.get("/", tags=["General"])
def read_root():
    return {
        "message": "Bienvenido a OrthoConnect API",
        "docs": "/docs",
        "status": "online"
    }