"""front/api_client.py — Único puente entre Streamlit y la API (Streamlit nunca habla con Mongo)."""
import os
from urllib.parse import quote

import requests

# 127.0.0.1 y no "localhost": en Windows "localhost" prueba primero IPv6 (::1) y, como uvicorn escucha
# solo en IPv4, cada petición tardaba unos 2 segundos de más.
URL_BASE = os.getenv("API_URL", "http://127.0.0.1:8000")


def get(ruta: str, **params):
    return requests.get(f"{URL_BASE}{ruta}", params=params, timeout=10)


def post(ruta: str, datos: dict):
    return requests.post(f"{URL_BASE}{ruta}", json=datos, timeout=10)


def api_en_linea() -> bool:
    try:
        return get("/").status_code == 200
    except requests.RequestException:
        return False


def detalle_error(respuesta) -> str:
    """El "detail" de un 404/409 es texto y el de un 422 de Pydantic es una lista de objetos con
    "msg": ambos se vuelven una sola línea legible."""
    try:
        detalle = respuesta.json().get("detail")
    except ValueError:
        detalle = None
    if isinstance(detalle, list):
        texto = "; ".join(str(e.get("msg", e)) if isinstance(e, dict) else str(e) for e in detalle)
    else:
        texto = str(detalle) if detalle else f"La API respondió con el código {respuesta.status_code}"
    return texto.rstrip(".") + "."


def buscar_asesor(correo: str, codigo: str) -> dict | None:
    """Ingreso de asesor para la demostración: busca en GET /asesores/ el asesor ACTIVO cuyo correo
    y código coincidan. Devuelve solo {id, nombre}; el código no sale de esta función."""
    correo, codigo = correo.strip().lower(), codigo.strip()
    for a in get("/asesores/").json():
        if a["correo"].lower() == correo and a["codigo"] == codigo and a.get("activo", True):
            return {"id": a["id"], "nombre": a["nombre"]}
    return None


def codigo_asesor_actual(asesor_id: str) -> str | None:
    """Pagos y cancelaciones piden el código del asesor (campo usuario). Se lee de la API justo antes de
    usarlo: devuelve el código solo si ese asesor existe y sigue activo. No se guarda ni se muestra."""
    for a in get("/asesores/").json():
        if a["id"] == asesor_id:
            return a["codigo"] if a.get("activo", True) else None
    return None


def mapa_asesores() -> dict:
    """{código: nombre} para mostrar el historial de una reserva con nombres en vez de códigos."""
    return {a["codigo"]: a["nombre"] for a in get("/asesores/").json()}


def listar_reservas(estado: str | None = None, documento: str | None = None, limite: int = 50):
    params = {"estado": estado, "cliente": documento, "limite": limite}
    return get("/reservas/", **{k: v for k, v in params.items() if v is not None})


def obtener_reserva(codigo: str):
    return get(f"/reservas/{quote(codigo, safe='')}")   # el código lo digita el asesor


def registrar_pago(codigo: str, valor: int, medio: str, usuario: str):
    return post(f"/reservas/{quote(codigo, safe='')}/pagos", {"valor": valor, "medio": medio, "usuario": usuario})


def cancelar_reserva(codigo: str, usuario: str):
    return post(f"/reservas/{quote(codigo, safe='')}/cancelar", {"usuario": usuario})


# ─────────────── Catálogo y clientes: listados (GET) y registros (POST) ───────────────
# Los registros reciben el cuerpo ya validado con el DTO del backend (model_dump(mode="json")).
def listar_ciudades():
    return get("/ciudades/")


def listar_vuelos(limite: int = 200):
    return get("/vuelos/", limite=limite)


def listar_hoteles():
    return get("/hoteles/")


def listar_tours():
    return get("/tours/")


def listar_salidas(tour_id: str, solo_futuras: bool = True):
    return get(f"/tours/{tour_id}/salidas", solo_futuras=str(solo_futuras).lower())


def listar_paquetes(solo_vigentes: bool = True):
    return get("/paquetes/", solo_vigentes=str(solo_vigentes).lower())


def listar_clientes():
    return get("/clientes/")


def crear_vuelo(datos: dict):
    return post("/vuelos/", datos)


def crear_hotel(datos: dict):
    return post("/hoteles/", datos)


def generar_noches(hotel_id: str, datos: dict):
    return post(f"/hoteles/{hotel_id}/noches", datos)


def crear_tour(datos: dict):
    return post("/tours/", datos)


def crear_salida(tour_id: str, datos: dict):
    return post(f"/tours/{tour_id}/salidas", datos)


def crear_paquete(datos: dict):
    return post("/paquetes/", datos)


def crear_cliente(datos: dict):
    return post("/clientes/", datos)
