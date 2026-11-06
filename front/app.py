"""front/app.py — Inicio de Brújula Viajes (herramienta de los asesores). Correr desde front/:  streamlit run app.py"""
import requests
import streamlit as st

import api_client
from estilo import BUSCAR, CATALOGO, REPORTES, RESERVAS, SLOGAN, aplicar_estilo

st.set_page_config(page_title="Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
asesor = st.session_state.get("asesor")

# --- Encabezado: logo y estado de la API ---
logo, estado = st.columns([3, 2], vertical_alignment="center")
logo.image("assets/logo_principal.png", width=270)
with estado, st.container(horizontal_alignment="right"):
    if api_client.api_en_linea():
        st.badge("Sistema en línea", icon=":material/check_circle:", color="green")
    else:
        st.badge("Sin conexión con la API", icon=":material/cloud_off:", color="orange",
                 help="Levanta la API desde back/ con: uvicorn main:app --reload")

# --- Hero: slogan, ingreso o saludo del asesor, e ilustración ---
texto, ilustracion = st.columns(2, gap="large", vertical_alignment="center")
with texto:
    st.title(SLOGAN)
    if asesor:
        st.subheader(f"Hola, {asesor['nombre']}")
        st.write("Tu mesa de trabajo está lista: consulta el catálogo, registra reservas y revisa las cifras.")
        with st.container(key="cta_buscar"):
            st.page_link(BUSCAR, label="Registrar una reserva", icon=":material/travel_explore:")
    else:
        with st.container(border=True, key="panel_ingreso"):
            st.subheader("Ingreso de asesor")
            with st.form("ingreso", clear_on_submit=True, border=False):
                correo = st.text_input("Correo")
                codigo = st.text_input("Código de asesor", type="password")
                if st.form_submit_button("Ingresar", type="primary"):
                    try:
                        encontrado = api_client.buscar_asesor(correo, codigo)
                    except requests.RequestException:
                        st.warning("No hay conexión con la API en este momento. Inténtalo de nuevo en un rato.")
                    else:
                        if encontrado:
                            st.session_state.asesor = encontrado        # solo id y nombre, nunca el código
                            st.rerun()
                        st.error("No encontramos un asesor activo con esos datos. Revisa tus datos e inténtalo de nuevo.")
with ilustracion, st.container(key="redondeada_hero"):
    st.image("assets/hero_ilustracion.png", width="stretch")

# --- Tu mesa de trabajo: accesos a los cuatro módulos ---
st.header("Tu mesa de trabajo")
MODULOS = [
    (BUSCAR, "Buscar y reservar", ":material/travel_explore:",
     "Consulta vuelos, hoteles, tours y paquetes con disponibilidad real y registra la reserva."),
    (RESERVAS, "Reservas", ":material/confirmation_number:",
     "Revisa el detalle de cada reserva, registra pagos y gestiona cancelaciones."),
    (CATALOGO, "Catálogo y clientes", ":material/inventory_2:",
     "Mantén al día los productos de la agencia y los datos de los clientes."),
    (REPORTES, "Reportes", ":material/bar_chart:",
     "Ventas por mes, destinos más vendidos y ocupación de los vuelos."),
]
for i, (columna, (pagina, nombre, icono, frase)) in enumerate(zip(st.columns(4, gap="medium"), MODULOS)):
    with columna, st.container(border=True, height="stretch", key=f"tarjeta_modulo_{i}"):
        st.markdown(f"#### :primary[{icono}] {nombre}")
        st.write(frase)
        st.page_link(pagina, label="Abrir", icon=":material/arrow_forward:")

st.space("medium")


# --- Footer ---
isotipo, firma = st.columns([1, 14], vertical_alignment="center")
isotipo.image("assets/logo_isotipo.png", width=56)
firma.markdown(f"**Brújula Viajes** · :primary[{SLOGAN}]  \nVuelos, hoteles, tours y paquetes.")
