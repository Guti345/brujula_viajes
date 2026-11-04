"""front/api_client.py — Único puente entre Streamlit y la API (Streamlit nunca habla con Mongo)."""
import os

import requests

URL_BASE = os.getenv("API_URL", "http://localhost:8000")


def get(ruta: str, **params):
    return requests.get(f"{URL_BASE}{ruta}", params=params, timeout=10)


def post(ruta: str, datos: dict):
    return requests.post(f"{URL_BASE}{ruta}", json=datos, timeout=10)


def api_en_linea() -> bool:
    try:
        return get("/").status_code == 200
    except requests.RequestException:
        return False
