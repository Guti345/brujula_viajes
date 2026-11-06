"""front/pages/04_Reportes.py — Reportes (la funcionalidad llega en la siguiente fase)."""
import streamlit as st

from estilo import aplicar_estilo, encabezado_modulo, requerir_asesor

st.set_page_config(page_title="Reportes · Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
requerir_asesor()
encabezado_modulo("Reportes", "Las ventas, los destinos y la ocupación, en cifras claras.")

st.info("Este módulo se habilita en la siguiente fase. Mientras tanto, puedes recorrer las demás secciones "
        "desde el menú lateral.", icon=":material/construction:")
