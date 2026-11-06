"""front/pages/03_Catalogo_y_clientes.py — Catálogo y clientes (la funcionalidad llega en la siguiente fase)."""
import streamlit as st

from estilo import aplicar_estilo, encabezado_modulo, requerir_asesor

st.set_page_config(page_title="Catálogo y clientes · Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
requerir_asesor()
encabezado_modulo("Catálogo y clientes", "Mantén vuelos, hoteles, tours, paquetes y clientes siempre al día.")

st.info("Este módulo se habilita en la siguiente fase. Mientras tanto, puedes recorrer las demás secciones "
        "desde el menú lateral.", icon=":material/construction:")
