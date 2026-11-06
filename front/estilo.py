"""front/estilo.py — Identidad visual de Brújula Viajes: paleta, CSS breve, menú y encabezados.

El tema base (colores, radio y fuente Nunito Sans) vive en .streamlit/config.toml. Aquí solo va
lo que el tema no cubre. El CSS usa las clases st-key-<key> que Streamlit pone a los contenedores
con key, así que si una regla deja de aplicar, la página se ve normal y nada se rompe.
"""
from datetime import datetime, timedelta, timezone

import streamlit as st

BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")   # igual que el backend: sin horario de verano

AZUL_MARINO = "#0A2540"
TURQUESA = "#00A896"
AMARILLO = "#FFD166"
CORAL = "#FF6B6B"
ARENA = "#F4F1DE"
BLANCO = "#FFFFFF"

SLOGAN = "Tu rumbo a recuerdos inolvidables."

INICIO = "app.py"
BUSCAR = "pages/01_Buscar_y_reservar.py"
RESERVAS = "pages/02_Reservas.py"
CATALOGO = "pages/03_Catalogo_y_clientes.py"
REPORTES = "pages/04_Reportes.py"

CSS = f"""
<style>
/* Tarjetas: st.container(border=True, key="tarjeta_...") */
[class*="st-key-tarjeta"] {{
    background: {ARENA};
    border-radius: 16px;
    box-shadow: 0 2px 10px rgba(10, 37, 64, 0.06);
}}

/* Paneles con campos: st.container(border=True, key="panel_..."). Fondo blanco, porque los
   campos de Streamlit ya usan el arena y sobre arena no se distinguen. */
[class*="st-key-panel"] {{
    border-radius: 16px;
    box-shadow: 0 2px 10px rgba(10, 37, 64, 0.06);
}}

/* Resumen de la reserva en curso (Buscar y reservar): queda pegado arriba al bajar y, si crece más
   que la pantalla, tiene su propio scroll. Si sticky no opera, el panel se ve igual que antes.
   El contenedor usa height="stretch" para que su envoltorio ocupe el alto de la columna (ese es el
   recorrido del sticky); flex: 0 0 auto evita que el panel mismo crezca y mida solo su contenido.
   max-height descuenta el top (4rem), el relleno inferior de la página (10rem) y 1rem de aire, para
   que al final de la página el panel quepa completo sin que lo empuje hacia arriba. */
.st-key-resumen_panel {{
    flex: 0 0 auto;
    position: sticky;
    top: 4rem;
    max-height: calc(100vh - 15rem);
    overflow-y: auto;
}}

/* Botones de Streamlit */
.stButton button, .stFormSubmitButton button {{
    border-radius: 12px;
    font-weight: 700;
}}

/* Enlace principal con forma de botón: st.container(key="cta_...") con un st.page_link */
[class*="st-key-cta"] a {{
    background: {TURQUESA};
    border-radius: 12px;
    padding: 0.55rem 1.4rem;
}}
[class*="st-key-cta"] a, [class*="st-key-cta"] a * {{
    color: {BLANCO} !important;
    font-weight: 700;
}}
[class*="st-key-cta"] a:hover {{ background: #00917F; }}

/* Imágenes con esquinas redondeadas: st.container(key="redondeada_...") */
[class*="st-key-redondeada"] img {{ border-radius: 18px; }}
</style>
"""


def aplicar_estilo():
    """CSS de marca, menú lateral común e insignia del asesor activo. Va justo después de
    st.set_page_config en cada página."""
    st.html(CSS)
    with st.sidebar:
        st.page_link(INICIO, label="Inicio", icon=":material/home:")
        st.page_link(BUSCAR, label="Buscar y reservar", icon=":material/travel_explore:")
        st.page_link(RESERVAS, label="Reservas", icon=":material/confirmation_number:")
        st.page_link(CATALOGO, label="Catálogo y clientes", icon=":material/inventory_2:")
        st.page_link(REPORTES, label="Reportes", icon=":material/bar_chart:")
        asesor = st.session_state.get("asesor")
        if asesor:
            st.divider()
            st.markdown(f":material/badge: **Asesor:** {asesor['nombre']}")
            if st.button("Salir", icon=":material/logout:"):
                # Todo lo de la sesión es estado de operación (asesor, reserva en curso, cliente,
                # pasajeros, avisos y claves de widgets): se borra completo para que el siguiente
                # asesor empiece de cero. Luego vuelve al Inicio público.
                st.session_state.clear()
                st.switch_page(INICIO)


def requerir_asesor() -> dict:
    """Puerta de los módulos: sin asesor en sesión no se renderiza nada más de la página. Es un
    control de la interfaz para la demostración académica; la API sigue abierta."""
    asesor = st.session_state.get("asesor")
    if not asesor:
        st.info("Esta sección es para el equipo de asesores. Ingresa desde el Inicio.", icon=":material/badge:")
        st.page_link(INICIO, label="Ir al Inicio", icon=":material/login:")
        st.stop()
    return asesor


def pesos(valor, markdown: bool = False) -> str:
    """Pesos colombianos con punto de miles: 1234567 -> $ 1.234.567. Dentro de st.markdown, dos "$"
    se leen como una fórmula LaTeX; con markdown=True el signo va escapado."""
    # Espacio no separable: el signo y la cifra nunca quedan en líneas distintas
    return ("\\$\u00a0" if markdown else "$\u00a0") + f"{round(valor):,}".replace(",", ".")


def hora_bogota(iso: str) -> str:
    """Fecha ISO con zona (como la manda la API) en hora de Bogotá: 16/11/2026 07:00"""
    return datetime.fromisoformat(iso).astimezone(BOGOTA).strftime("%d/%m/%Y %H:%M")


def encabezado_modulo(titulo: str, mensaje: str):
    """Encabezado de las páginas de módulo: isotipo, título, slogan y un mensaje propio."""
    isotipo, texto = st.columns([1, 12], vertical_alignment="center")
    isotipo.image("assets/logo_isotipo.png", width=70)
    with texto:
        st.title(titulo)
        st.markdown(f"**:primary[{SLOGAN}]** {mensaje}")
    st.divider()
