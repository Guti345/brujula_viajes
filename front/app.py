"""front/app.py — Portada de Brújula Viajes. Correr desde front/:  streamlit run app.py"""
import streamlit as st

import api_client

st.set_page_config(page_title="Brújula Viajes", page_icon="🧭", layout="wide")
st.title("Brújula Viajes")
st.caption("Vuelos nacionales, hoteles, tours y paquetes")

if api_client.api_en_linea():
    st.success("API en línea")
    ciudades = api_client.get("/ciudades/").json()
    st.write(f"Destinos disponibles: {', '.join(c['nombre'] for c in ciudades) or 'ninguno aún'}")
else:
    st.error("La API no responde. Levántala desde back/ con:  uvicorn main:app --reload")

st.info("Las páginas de catálogo y reservas se agregan en el módulo de Streamlit.")
