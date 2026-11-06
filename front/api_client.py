"""front/api_client.py — Único puente entre Streamlit y la API (Streamlit nunca habla con Mongo)."""
import os

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
