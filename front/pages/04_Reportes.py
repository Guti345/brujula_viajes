"""front/pages/04_Reportes.py — Reportes B1-B3: ventas por mes, destinos más vendidos y ocupación de vuelos."""
import math

import altair as alt
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

import api_client
from estilo import AZUL_MARINO, CORAL, TURQUESA, aplicar_estilo, encabezado_modulo, pesos, requerir_asesor

st.set_page_config(page_title="Reportes · Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
requerir_asesor()
encabezado_modulo("Reportes", "Las ventas, los destinos y la ocupación, en cifras claras.")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
SERIES = ["Total vendido", "Reservas"]
# Lado del círculo donde va el nombre: Cartagena y Santa Marta están cerca, así que sus nombres van
# hacia lados opuestos. Las ciudades que no aparecen aquí llevan el nombre a la derecha.
NOMBRE_A_LA_IZQUIERDA = {"CTG", "MDE", "CLO"}
RADIO_MAX = 90_000          # metros, para el destino con más ingresos (no alcanza a tocar Cartagena-Santa Marta)
RADIO_MIN_PX = 4            # el mapa nunca dibuja un círculo de menos de 4 px
TONO_MIN, TONO_MAX = (0x78, 0xD3, 0xC7), (0x00, 0x6E, 0x63)   # turquesa claro -> intenso (paleta de marca)
ALFA = 220
VISTA = {"latitude": 8.0, "longitude": -77.6, "zoom": 4.9}    # vista fija sobre Colombia, San Andrés incluida
# Tamaños comunes a las tres pestañas
ALTO_GRAFICO = 440
ALTO_MAPA = 500
FILA_BARRA = 56


class RespuestaInvalida(Exception):
    pass


@st.cache_data(ttl=20, show_spinner=False)
def leer(consulta: str):
    """GET de solo lectura con caché corta, por nombre del helper de api_client. Los fallos salen como
    excepción, que st.cache_data no guarda: cuando la API vuelve, la siguiente carga consulta de nuevo."""
    r = getattr(api_client, consulta)()
    if r.status_code != 200:
        raise RespuestaInvalida(api_client.detalle_error(r))
    return r.json()


def consultar(consulta: str, que: str, aviso: bool = True):
    """Datos de una sección, o None con un aviso propio de esa sección: las demás siguen funcionando."""
    try:
        return leer(consulta)
    except requests.RequestException:
        motivo = "no hay conexión con la API (puede estar apagada o tardar demasiado en responder)"
    except RespuestaInvalida as e:
        motivo = str(e)
    if aviso:
        st.warning(f"No fue posible cargar {que}: {motivo.rstrip('.')}. Recarga la página para intentarlo de nuevo.",
                   icon=":material/cloud_off:")
    return None


def porcentaje(valor: float) -> str:
    """53.8 -> 53,8 % (coma decimal y espacio no separable antes del signo)"""
    return f"{valor:.1f}".replace(".", ",") + " %"


def coordenada(ciudad: dict) -> tuple[float, float] | None:
    """(latitud, longitud) de la ubicación GeoJSON que entrega GET /ciudades/, o None si la ciudad no la
    tiene. GeoJSON guarda [longitud, latitud]: primero la longitud."""
    try:
        lon, lat = ciudad["ubicacion"]["coordinates"]
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lon


def tono(fraccion: float) -> list[int]:
    """Turquesa entre el tono claro (fracción 0) y el intenso (fracción 1)."""
    return [round(a + (b - a) * fraccion) for a, b in zip(TONO_MIN, TONO_MAX)] + [ALFA]


def con_letra(grafico):
    """Misma tipografía y aire en los gráficos de las tres pestañas."""
    return (grafico.configure_axis(labelFontSize=13, titleFontSize=14, titlePadding=12, labelPadding=6)
            .configure_legend(labelFontSize=14, symbolSize=200, padding=8)
            .configure_view(strokeWidth=0))


def radio_en_pixeles(radio_m: float, lat: float) -> float:
    """Radio en pantalla con la vista inicial del mapa: deck.gl usa teselas de 512 px y escala Mercator,
    así que un metro ocupa más píxeles lejos del ecuador. Mismo piso de RADIO_MIN_PX que el mapa."""
    metros_por_px = 40_075_016.686 * math.cos(math.radians(lat)) / (512 * 2 ** VISTA["zoom"])
    return max(radio_m / metros_por_px, RADIO_MIN_PX)


def leyenda_tamano(puntos: list[dict]) -> str:
    """Círculos con el tamaño REAL de tres destinos del mapa (el mayor, uno intermedio y el menor): el
    área sigue siendo proporcional a los ingresos. Sin color de relleno, para no mezclarlo con pasajeros.
    Son divs redondeados: st.html descarta el SVG."""
    orden = sorted(puntos, key=lambda p: -p["ingresos"])
    muestra = [orden[k] for k in sorted({0, len(orden) // 2, len(orden) - 1})]
    radios = [radio_en_pixeles(p["radio"], p["lat"]) for p in muestra]
    caja = 2 * max(radios) + 4
    filas = [f'<div style="display: flex; align-items: center; gap: 12px; margin: 6px 0">'
             f'<span style="width: {caja:.0f}px; height: {2 * r + 4:.0f}px; display: flex; align-items: center; '
             f'justify-content: center; flex: none"><span style="width: {2 * r:.1f}px; height: {2 * r:.1f}px; '
             f'border-radius: 50%; border: 1.5px solid {AZUL_MARINO}; background: rgba(10, 37, 64, 0.05); '
             f'box-sizing: border-box"></span></span>'
             f'<span style="font-size: 13px"><b>{p["ingresos_txt"]}</b> · {p["nombre"]}</span></div>'
             for p, r in zip(muestra, radios)]
    return (f'<div style="font-family: inherit; color: {AZUL_MARINO}">'
            f'<div style="font-weight: 700; margin-bottom: 4px">Área del círculo = ingresos</div>'
            f'{"".join(filas)}'
            f'<div style="font-size: 12px; color: #5B6B7C; margin-top: 4px">Tamaños reales con el zoom con el que '
            f'abre el mapa.</div></div>')


def leyenda_intensidad(puntos: list[dict]) -> str:
    """Una muestra por destino con el mismo color (y transparencia) con que el mapa lo pinta."""
    filas = []
    for p in sorted(puntos, key=lambda p: (p["pasajeros"], p["nombre"])):
        r, g, b, a = p["color"]
        filas.append(f'<div style="display: flex; align-items: center; gap: 10px; margin: 5px 0">'
                     f'<span style="width: 22px; height: 22px; border-radius: 50%; flex: none; '
                     f'background: rgba({r}, {g}, {b}, {a / 255:.3f}); box-shadow: 0 0 0 2px #fff, 0 0 0 3px #D5DCE3">'
                     f'</span><span style="font-size: 13px"><b>{p["pasajeros"]} pasajeros</b> · {p["nombre"]}</span></div>')
    claro, intenso = (f"rgba({r}, {g}, {b}, {ALFA / 255:.3f})" for r, g, b in (TONO_MIN, TONO_MAX))
    return (f'<div style="font-family: inherit; color: {AZUL_MARINO}">'
            f'<div style="font-weight: 700; margin-bottom: 6px">Intensidad del turquesa = pasajeros</div>'
            f'{"".join(filas)}'
            f'<div style="display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: #5B6B7C">'
            f'<span>menos</span><span style="flex: 1; height: 8px; border-radius: 4px; '
            f'background: linear-gradient(90deg, {claro}, {intenso})"></span><span>más intenso = más pasajeros</span>'
            f'</div></div>')


t_ventas, t_destinos, t_ocupacion = st.tabs(
    [":material/payments: Ventas por mes", ":material/travel_explore: Destinos más vendidos",
     ":material/airline_seat_recline_normal: Ocupación de vuelos"])

# ─────────────────────────────── B1: ventas por mes ───────────────────────────────
with t_ventas:
    st.subheader("Ventas por mes")
    ventas = consultar("reporte_ventas_por_mes", "las ventas por mes")
    if ventas == []:
        st.info("Aún no hay ventas registradas (sin contar reservas canceladas).", icon=":material/info:")
    elif ventas:
        etiquetas = [f"{MESES[v['mes'] - 1]} {v['anio']}" for v in ventas]
        if len(ventas) > 1:
            desde, hasta = st.select_slider("Periodo (desde – hasta)", options=etiquetas,
                                            value=(etiquetas[0], etiquetas[-1]), key="b1_periodo", width=520)
            i, j = etiquetas.index(desde), etiquetas.index(hasta)
        else:
            i = j = 0
            st.caption(f"Solo hay ventas en {etiquetas[0]}.")
        df = pd.DataFrame([{"mes": etiquetas[k], "total_vendido": ventas[k]["total_vendido"], "reservas": ventas[k]["reservas"],
                            "total_txt": pesos(ventas[k]["total_vendido"])} for k in range(i, j + 1)])
        orden = list(df["mes"])
        # Rótulo en dos líneas (mes / año) para que ninguno se oculte por falta de ancho
        eje_x = alt.X("mes:N", sort=orden, title="Mes", axis=alt.Axis(labelAngle=0, labelExpr="split(datum.label, ' ')",
                                                                      labelLimit=220))
        ayuda = [alt.Tooltip("mes:N", title="Mes"), alt.Tooltip("total_txt:N", title="Total vendido"),
                 alt.Tooltip("reservas:Q", title="Reservas")]

        tabla, grafico = st.columns(2, gap="large")
        with tabla, st.container(border=True, key="panel_rep_b1_tabla", height="stretch"):
            st.table([{"Mes": f["mes"], "Total vendido": pesos(f["total_vendido"], markdown=True), "Reservas": f["reservas"]}
                      for f in df.to_dict("records")], hide_index=True)
            st.caption(f"En el periodo: {pesos(df['total_vendido'].sum(), markdown=True)} vendidos en "
                       f"{df['reservas'].sum()} reservas.")
            st.caption("Ventas = total de las reservas creadas en el mes; no es dinero recaudado (los pagos son otro "
                       "dato). No incluye reservas canceladas.")
            st.caption("El número de reservas no equivale a clientes únicos.")
        with grafico, st.container(border=True, key="panel_rep_b1_grafico"):
            # Dos barras por mes (lado a lado con xOffset), cada una con su propio eje Y
            base = alt.Chart(df).encode(
                x=eje_x, tooltip=ayuda,
                xOffset=alt.XOffset("serie:N", scale=alt.Scale(domain=SERIES, paddingInner=0.04)),
                color=alt.Color("serie:N", scale=alt.Scale(domain=SERIES, range=[TURQUESA, CORAL]),
                                legend=alt.Legend(title=None, orient="top")))
            barra = {"cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4}
            total = base.transform_calculate(serie="'Total vendido'").mark_bar(**barra).encode(
                y=alt.Y("total_vendido:Q", title="Total vendido (COP)", axis=alt.Axis(
                    orient="left", labelExpr="'$ ' + replace(format(datum.value, ',.0f'), regexp(',', 'g'), '.')")))
            cuantas = base.transform_calculate(serie="'Reservas'").mark_bar(**barra).encode(
                y=alt.Y("reservas:Q", title="Reservas", axis=alt.Axis(orient="right", format="d", tickMinStep=1)))
            st.altair_chart(con_letra(alt.layer(total, cuantas).resolve_scale(y="independent")
                                      .properties(height=ALTO_GRAFICO)), width="stretch")

# ─────────────────────────────── B2: destinos más vendidos ───────────────────────────────
with t_destinos:
    st.subheader("Destinos más vendidos")
    destinos = consultar("reporte_destinos_mas_vendidos", "los destinos más vendidos")
    if destinos == []:
        st.info("Aún no hay destinos con ventas (sin contar reservas canceladas).", icon=":material/info:")
    elif destinos:
        ciudades = consultar("listar_ciudades", "los nombres de las ciudades", aviso=False)
        if ciudades is None:
            st.caption("No se pudieron consultar las ciudades: se muestran sus códigos y no hay coordenadas para el mapa.")
        nombres = {c["iata"]: c["nombre"] for c in ciudades or []}
        nombre = lambda iata: nombres.get(iata, iata)
        # Coordenadas solo desde la API: una ciudad sin ubicación no se dibuja
        coordenadas = {c["iata"]: coordenada(c) for c in ciudades or [] if coordenada(c)}

        # Arriba el mapa con su leyenda al lado; abajo el ranking a todo el ancho
        mapa, leyenda = st.columns([2, 1], gap="large")
        with mapa, st.container(border=True, key="panel_rep_b2_mapa"):
            sin_coordenada = [nombre(d["ciudad"]) for d in destinos if d["ciudad"] not in coordenadas]
            if sin_coordenada:
                st.warning(f"No hay coordenadas para {', '.join(sin_coordenada)}: no se dibuja en el mapa, pero sí "
                           "aparece en el ranking.", icon=":material/location_off:")
            # pydeck lee como expresión todo texto sin comillas: los valores literales van entre comillas
            en_mapa = [d for d in destinos if d["ciudad"] in coordenadas]
            if en_mapa:
                mas_ingresos = max(d["ingresos"] for d in en_mapa) or 1
                menos_pas, mas_pas = min(d["pasajeros"] for d in en_mapa), max(d["pasajeros"] for d in en_mapa)
                puntos = []
                for d in en_mapa:
                    lat, lon = coordenadas[d["ciudad"]]
                    radio = RADIO_MAX * math.sqrt(max(d["ingresos"], 0) / mas_ingresos)   # área ∝ ingresos
                    izquierda = d["ciudad"] in NOMBRE_A_LA_IZQUIERDA
                    # El nombre se ancla al borde del círculo (en metros), así no lo tapa con ningún zoom
                    borde = radio / (111_320 * math.cos(math.radians(lat)))
                    puntos.append({"nombre": nombre(d["ciudad"]), "lat": lat, "lon": lon, "radio": radio,
                                   "ingresos": d["ingresos"], "ingresos_txt": pesos(d["ingresos"]),
                                   "pasajeros": d["pasajeros"],
                                   "color": tono((d["pasajeros"] - menos_pas) / (mas_pas - menos_pas) if mas_pas > menos_pas else 1),
                                   "lon_nombre": lon - borde if izquierda else lon + borde,
                                   "ancla": "end" if izquierda else "start", "corrimiento": [-6 if izquierda else 6, 0]})
                circulos = pdk.Layer("ScatterplotLayer", data=puntos, get_position=["lon", "lat"], get_radius="radio",
                                     get_fill_color="color", stroked=True, get_line_color=[255, 255, 255],
                                     line_width_min_pixels=2, radius_min_pixels=RADIO_MIN_PX, pickable=True)
                rotulos = pdk.Layer("TextLayer", data=puntos, get_position=["lon_nombre", "lat"], get_text="nombre",
                                    get_size=15, get_color=list(int(AZUL_MARINO[k:k + 2], 16) for k in (1, 3, 5)),
                                    get_text_anchor="ancla", get_alignment_baseline="'center'",
                                    get_pixel_offset="corrimiento", character_set="'auto'",   # tildes: "Bogotá"
                                    font_family="'Nunito Sans, sans-serif'", font_weight=700)
                ayuda_mapa = {"html": "<b>{nombre}</b><br/>Ingresos: {ingresos_txt}<br/>Pasajeros: {pasajeros}",
                              "style": {"backgroundColor": AZUL_MARINO, "color": "white", "fontSize": "14px"}}
                st.pydeck_chart(pdk.Deck(layers=[circulos, rotulos], initial_view_state=pdk.ViewState(**VISTA),
                                         tooltip=ayuda_mapa, map_provider="carto",
                                         map_style=pdk.map_styles.CARTO_LIGHT_NO_LABELS), height=ALTO_MAPA)
                st.caption("Tamaño del círculo: ingresos (el área es proporcional a los ingresos). Intensidad del "
                           "turquesa: pasajeros (más intenso = más pasajeros). Señala un círculo para ver sus cifras.")
                st.caption("El fondo del mapa usa teselas de Carto y necesita internet en el navegador. Si no se ve, "
                           "el ranking tiene las mismas cifras.")
                with leyenda, st.container(border=True, key="panel_rep_b2_leyenda"):
                    st.html(leyenda_tamano(puntos))
                    st.divider()
                    st.html(leyenda_intensidad(puntos))
        with st.container(border=True, key="panel_rep_b2_ranking"):
            st.markdown("**Ranking por ingresos**")
            st.table([{"Puesto": k, "Destino": nombre(d["ciudad"]), "Ingresos": pesos(d["ingresos"], markdown=True),
                       "Pasajeros": d["pasajeros"]} for k, d in enumerate(destinos, start=1)], hide_index=True)
            st.caption("Pasajeros contados por ítems de vuelo y paquete; una misma persona puede contarse más de una "
                       "vez. No incluye reservas canceladas. Solo los 5 destinos con más ingresos.")

# ─────────────────────────────── B3: ocupación de vuelos ───────────────────────────────
with t_ocupacion:
    st.subheader("Ocupación de vuelos")
    ocupacion = consultar("reporte_ocupacion_vuelos", "la ocupación de vuelos")
    if ocupacion == []:
        st.info("Aún no hay vuelos registrados.", icon=":material/info:")
    elif ocupacion:
        with st.container(border=True, key="panel_rep_b3_tabla"):
            st.markdown("**Reporte oficial por vuelo**")
            st.table([{"Código": o["codigo"], "Sillas totales": o["sillas_totales"], "Vendidas": o["vendidas"],
                       "Ocupación": porcentaje(o["ocupacion_pct"]) if o["sillas_totales"] else "No calculable (0 sillas)"}
                      for o in ocupacion], hide_index=True)
            st.caption("Ordenado de mayor a menor ocupación. Las reservas canceladas ya están excluidas porque el "
                       "inventario recupera sus sillas.")

        with st.container(border=True, key="panel_rep_b3_aerolineas"):
            st.markdown("**Ocupación por aerolínea**")
            vuelos = consultar("listar_vuelos", "los vuelos", aviso=False)
            por_codigo = {v["codigo"]: v for v in vuelos or []}
            if vuelos is None or set(por_codigo) != {o["codigo"] for o in ocupacion}:
                st.warning("No fue posible cruzar íntegramente el reporte con el catálogo de vuelos, así que esta vista no "
                           "se muestra (sumaría solo una parte de los vuelos). La tabla oficial de arriba sigue completa.",
                           icon=":material/link_off:")
            else:
                rutas = sorted({f"{v['origen']} → {v['destino']}" for v in vuelos})
                ruta = st.selectbox("Ruta (opcional)", ["Todos"] + rutas, key="b3_ruta", width=320,
                                    help="Cada sentido es una ruta distinta: la ida y el regreso se ven por separado.")
                grupos, sin_sillas = {}, []
                for o in ocupacion:
                    v = por_codigo[o["codigo"]]
                    if ruta != "Todos" and f"{v['origen']} → {v['destino']}" != ruta:
                        continue
                    g = grupos.setdefault(v["aerolinea"], {"vendidas": 0, "totales": 0, "vuelos": 0})
                    if o["sillas_totales"] == 0:        # división por cero: no es una ocupación real de 0 %
                        sin_sillas.append(o["codigo"])
                        continue
                    g["vendidas"] += o["vendidas"]
                    g["totales"] += o["sillas_totales"]
                    g["vuelos"] += 1
                filas = []
                for aerolinea, g in grupos.items():
                    # Ponderado por sillas: suma de vendidas / suma de sillas (nunca promedio de porcentajes)
                    pct = 100 * g["vendidas"] / g["totales"] if g["totales"] else None
                    filas.append({"aerolinea": aerolinea, "pct": pct, "x_rotulo": pct or 0, "vuelos": g["vuelos"],
                                  "rotulo": f"{porcentaje(pct)} ({g['vendidas']}/{g['totales']})" if pct is not None
                                  else "N/D (sin dato: sus vuelos no tienen sillas)"})
                filas.sort(key=lambda f: (f["pct"] is None, -(f["pct"] or 0), f["aerolinea"]))
                df = pd.DataFrame(filas)
                eje_y = alt.Y("aerolinea:N", sort=list(df["aerolinea"]), title="Aerolínea",
                              axis=alt.Axis(labelLimit=320))
                ayuda = [alt.Tooltip("aerolinea:N", title="Aerolínea"), alt.Tooltip("rotulo:N", title="Ocupación"),
                         alt.Tooltip("vuelos:Q", title="Vuelos con sillas")]
                barras = alt.Chart(df).mark_bar(color=TURQUESA, cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                    y=eje_y, tooltip=ayuda,
                    x=alt.X("pct:Q", title="Ocupación (%)", scale=alt.Scale(domain=[0, 100])))
                rotulos = alt.Chart(df).mark_text(align="left", dx=8, color=AZUL_MARINO, fontWeight=700,
                                                  fontSize=14).encode(y=eje_y, x="x_rotulo:Q", text="rotulo:N",
                                                                       tooltip=ayuda)
                st.altair_chart(con_letra((barras + rotulos).properties(height=alt.Step(FILA_BARRA))), width="stretch")
                if len(df) == 1:
                    st.info("Única aerolínea en esta selección.", icon=":material/info:")
                if sin_sillas:
                    st.caption(f"Se excluyeron del cálculo {len(sin_sillas)} vuelo(s) con 0 sillas: {', '.join(sin_sillas)}.")
                st.caption("Vista adicional calculada en la app sumando las cifras del reporte oficial por vuelo (que se "
                           "calcula en MongoDB). Las canceladas ya están excluidas porque el inventario recupera sus sillas. "
                           "Ocupación = vendidas / sillas de todos sus vuelos.")
