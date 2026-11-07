"""front/pages/03_Catalogo_y_clientes.py — Registro de vuelos, hoteles, tours, paquetes y clientes."""
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
import streamlit as st
from pydantic import ValidationError

import api_client
from estilo import (BOGOTA, NOMBRES_TIPO, REGLAS_DOCUMENTO, TIPOS_DOCUMENTO, aplicar_estilo, documento_cliente,
                    encabezado_modulo, hora_bogota, pesos, requerir_asesor, tipo_doc)

# Mismos DTO del backend para pre-validar antes de tocar la red
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from back.app import schemas  # noqa: E402

st.set_page_config(page_title="Catálogo y clientes · Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
requerir_asesor()
encabezado_modulo("Catálogo y clientes",
                  "Consulta lo que hay en el catálogo y registra vuelos, hoteles, tours, paquetes y clientes.")

if not api_client.api_en_linea():
    st.warning("No hay conexión con la API. Levántala desde back/ con `uvicorn main:app --reload` "
               "y recarga la página.", icon=":material/cloud_off:")
    st.stop()

TARIFAS = {"Basica": "Básica", "Clasica": "Clásica", "Flexible": "Flexible"}
TIPOS_HAB = ["Sencilla", "Doble", "Familiar", "Suite"]
HOY = datetime.now(BOGOTA).date()
CAMPOS = {"codigo": "el código", "aerolinea": "la aerolínea", "origen": "el origen", "destino": "el destino",
          "sale": "la salida", "llega": "la llegada", "nombre": "el nombre", "precio": "el precio",
          "equipaje": "el equipaje", "sillas": "las sillas", "ciudad": "la ciudad", "direccion": "la dirección",
          "estrellas": "las estrellas", "tipo": "el tipo", "capacidad": "la capacidad",
          "precio_noche": "el precio por noche", "cantidad": "la cantidad", "desde": "la fecha desde",
          "hasta": "la fecha hasta", "horas": "la duración", "lugar": "el lugar de encuentro",
          "fecha": "la fecha y hora", "cupos": "los cupos", "descuento": "el descuento",
          "documento": "el documento", "correo": "el correo", "telefono": "el teléfono"}
LISTAS = {"tarifas": "Tarifa", "habitaciones": "Habitación", "componentes": "Componente"}


@st.cache_data(ttl=20, show_spinner=False)
def leer(consulta: str, *args):
    """GET de solo lectura con caché corta, por nombre del helper de api_client. None si la API no
    responde o rechaza la consulta. La caché se limpia tras cada registro para ver lo nuevo."""
    try:
        r = getattr(api_client, consulta)(*args)
    except requests.RequestException:
        return None
    return r.json() if r.status_code == 200 else None


def aviso_validacion(e: ValidationError) -> str:
    """Primer error de Pydantic en una línea en español, con la fila (tarifa, habitación...) si aplica."""
    error = e.errors()[0]
    loc = error["loc"]
    fila = next((f"{LISTAS[a]} {b + 1}: " for a, b in zip(loc, loc[1:]) if a in LISTAS and isinstance(b, int)), "")
    campo = CAMPOS.get(str(loc[-1]), str(loc[-1])) if loc else ""
    tipo, ctx = error["type"], error.get("ctx", {})
    if tipo == "missing" or (tipo == "string_too_short" and ctx.get("min_length") == 1):
        detalle = f"{'faltan' if campo.startswith(('los ', 'las ')) else 'falta'} {campo}"
    elif tipo == "string_too_short":
        detalle = f"{campo} debe tener al menos {ctx['min_length']} caracteres"
    elif tipo == "string_too_long":
        detalle = f"{campo} admite máximo {ctx['max_length']} caracteres"
    elif campo == "el correo":
        detalle = "el correo no tiene un formato válido"
    else:
        detalle = error["msg"].removeprefix("Value error, ")
    return f"Revisa los datos. {fila}{detalle[0].upper()}{detalle[1:]}."


def sin_vacios(datos: dict) -> dict:
    """Quita los campos sin valor para que el DTO los reporte como faltantes (y no como tipo inválido)."""
    return {k: v for k, v in datos.items() if v is not None}


def con_hora(dia: date | None, hora) -> datetime | None:
    """Fecha y hora digitadas en hora de Bogotá -> datetime con zona (-05:00), como lo pide la API."""
    return datetime.combine(dia, hora, tzinfo=BOGOTA) if dia and hora else None


def lista_texto(texto: str) -> list[str]:
    return [x.strip() for x in texto.split(",") if x.strip()]


def fecha_dia(iso: str) -> str:
    """Fechas de día (vigencias, entradas) llegan como 00:00 UTC: se muestra el día tal cual."""
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def ya_paso(iso: str) -> bool:
    return datetime.fromisoformat(iso) <= datetime.now(timezone.utc)


def precio_paquete(componentes: list, descuento: float) -> int:
    """Misma fórmula del servidor: suma de los precios por persona menos el descuento, en pesos enteros."""
    return round(sum(c["precio"] for c in componentes) * (1 - descuento / 100))


def encabezado_tab(titulo: str, nota: str):
    st.subheader(titulo)
    st.caption(nota)


def aviso(pestana: str):
    """Mensaje de éxito del último registro, en la pestaña donde se hizo."""
    if st.session_state.get("cat_aviso", ("",))[0] == pestana:
        st.success(st.session_state.pop("cat_aviso")[1], icon=":material/check_circle:")


def registrar(llamada, *, pestana: str, prefijo: str, que: str, exito, pista_duplicado: str = ""):
    """Envía un registro ya validado. Con 201 limpia el formulario (claves con ese prefijo), deja el aviso
    y vuelve a consultar las listas; si no, muestra el motivo de la API en una línea."""
    try:
        r = llamada()
    except requests.RequestException:
        st.error(f"No hay conexión con la API: no se registró {que}. Inténtalo de nuevo.")
        return
    if r.status_code == 201:
        for clave in [k for k in st.session_state if str(k).startswith(prefijo)]:
            del st.session_state[clave]
        st.session_state.cat_aviso = (pestana, exito(r.json()))
        leer.clear()
        st.rerun()
    motivo = api_client.detalle_error(r)
    # El único índice único de esa colección explica el 409 genérico de duplicado
    if r.status_code == 409 and pista_duplicado and "identificador único" in motivo:
        motivo = f"{motivo} {pista_duplicado}"
    st.error(f"No se pudo registrar {que}: {motivo}", icon=":material/error:")


def sin_lista(datos, que: str) -> bool:
    if datos is None:
        st.warning(f"No se pudo consultar {que}. Inténtalo de nuevo en un momento.")
        return True
    if not datos:
        st.info(f"Aún no hay {que} registrados.")
        return True
    return False


def agregar_componente(componente: dict):
    st.session_state.pq_componentes.append({"id": uuid.uuid4().hex, **componente})


def quitar_componente(cid: str):
    st.session_state.pq_componentes = [c for c in st.session_state.pq_componentes if c["id"] != cid]


ciudades = leer("listar_ciudades") or []
nombres = {c["iata"]: c["nombre"] for c in ciudades}
iatas = list(nombres)


def ciudad(iata: str | None) -> str:
    return f"{nombres.get(iata, iata)} ({iata})" if iata else "Sin ciudad"


t_vuelos, t_hoteles, t_tours, t_paquetes, t_clientes = st.tabs(
    [":material/flight: Vuelos", ":material/hotel: Hoteles", ":material/hiking: Tours",
     ":material/luggage: Paquetes", ":material/group: Clientes"])

# ─────────────────────────────── Vuelos ───────────────────────────────
with t_vuelos:
    aviso("vuelos")
    encabezado_tab("Vuelos", "Precio por silla y sillas libres de cada tarifa. Horas en hora de Bogotá.")
    vuelos = leer("listar_vuelos")
    if not sin_lista(vuelos, "vuelos"):
        # st.table interpreta markdown en las celdas: el $ va escapado (dos $ en una celda serían una fórmula)
        def tarifa_txt(v: dict, nombre: str) -> str:
            t = next((t for t in v["tarifas"] if t["nombre"] == nombre), None)
            return f"{pesos(t['precio'], markdown=True)} · {t['libres']} de {t['sillas']} libres" if t else "—"
        st.table([{"Código": v["codigo"], "Aerolínea": v["aerolinea"], "Ruta": f"{v['origen']} → {v['destino']}",
                   "Sale": hora_bogota(v["sale"]), "Llega": hora_bogota(v["llega"]),
                   **{TARIFAS[n]: tarifa_txt(v, n) for n in TARIFAS}} for v in vuelos], hide_index=True)

    with st.expander("Registrar vuelo", icon=":material/add:", key="exp_vuelo"):
        n_tarifas = st.columns(4)[0].number_input("Número de tarifas", 1, 3, key="vu_n")
        with st.form("vu_form", border=False):
            cod_col, aer_col = st.columns(2)
            codigo = cod_col.text_input("Código del vuelo", key="vu_codigo", placeholder="Ej.: BV1240")
            aerolinea = aer_col.text_input("Aerolínea", key="vu_aerolinea")
            o_col, d_col = st.columns(2)
            origen = o_col.selectbox("Origen", iatas, index=None, format_func=ciudad, key="vu_origen",
                                     placeholder="Elige la ciudad")
            destino = d_col.selectbox("Destino", iatas, index=None, format_func=ciudad, key="vu_destino",
                                      placeholder="Elige la ciudad")
            sd, sh, ld, lh = st.columns(4)
            sale = con_hora(sd.date_input("Fecha de salida", value=None, min_value=HOY, format="DD/MM/YYYY",
                                          key="vu_sale_dia"),
                            sh.time_input("Hora de salida", value=None, step=300, key="vu_sale_hora"))
            llega = con_hora(ld.date_input("Fecha de llegada", value=None, min_value=HOY, format="DD/MM/YYYY",
                                           key="vu_llega_dia"),
                             lh.time_input("Hora de llegada", value=None, step=300, key="vu_llega_hora"))
            st.caption("Fechas y horas en hora de Bogotá.")
            tarifas = []
            for i in range(n_tarifas):
                nom, pre, equ, sil = st.columns([2, 2, 3, 2])
                tarifas.append(sin_vacios({
                    "nombre": nom.selectbox(f"Tarifa {i + 1}", list(TARIFAS), index=i, format_func=TARIFAS.get,
                                            key=f"vu_t{i}_nombre"),
                    "precio": pre.number_input("Precio por silla", min_value=0, step=10000, value=None,
                                               key=f"vu_t{i}_precio"),
                    "equipaje": equ.text_input("Equipaje", key=f"vu_t{i}_equipaje", placeholder="Ej.: Maleta de 23 kg"),
                    "sillas": sil.number_input("Sillas", min_value=0, step=1, value=None, key=f"vu_t{i}_sillas")}))
            enviar = st.form_submit_button("Registrar vuelo", type="primary", icon=":material/check:")
        if enviar:
            nombres_tarifa = [t["nombre"] for t in tarifas]
            if origen and origen == destino:
                st.warning("El origen y el destino deben ser distintos.")
            elif sale is None or llega is None:
                st.warning("Escribe la fecha y la hora de salida y de llegada.")
            elif llega <= sale:
                st.warning("La llegada debe ser posterior a la salida.")
            elif len(set(nombres_tarifa)) != len(nombres_tarifa):
                st.warning("Cada tarifa debe tener un nombre distinto.")
            else:
                try:
                    vuelo = schemas.VueloCreate(**sin_vacios({"codigo": codigo, "aerolinea": aerolinea, "origen": origen,
                                                              "destino": destino, "sale": sale, "llega": llega,
                                                              "tarifas": tarifas}))
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    registrar(lambda: api_client.crear_vuelo(vuelo.model_dump(mode="json")),
                              pestana="vuelos", prefijo="vu_", que="el vuelo",
                              exito=lambda v: f"Vuelo {v['codigo']} {v['origen']} → {v['destino']} registrado. "
                                              "Sus sillas quedan libres para la venta.",
                              pista_duplicado="Ya hay un vuelo con ese código.")

# ─────────────────────────────── Hoteles ───────────────────────────────
with t_hoteles:
    aviso("hoteles")
    encabezado_tab("Hoteles", "Tipos de habitación con su capacidad, precio por noche y cantidad.")
    hoteles = leer("listar_hoteles")
    if not sin_lista(hoteles, "hoteles"):
        st.table([{"Hotel": h["nombre"], "Ciudad": ciudad(h["ciudad"]), "Estrellas": "★" * h["estrellas"],
                   "Dirección": h["direccion"], "Servicios": ", ".join(h["servicios"]) or "—",
                   "Habitaciones": " · ".join(f"{x['tipo']}: {x['capacidad']} pers., {pesos(x['precio_noche'], markdown=True)} "
                                              f"por noche, {x['cantidad']} hab." for x in h["habitaciones"])}
                  for h in hoteles], hide_index=True)

    with st.expander("Registrar hotel", icon=":material/add:", key="exp_hotel"):
        st.info("Un hotel nuevo no tendrá disponibilidad hasta generar sus noches.", icon=":material/info:")
        n_hab = st.columns(4)[0].number_input("Tipos de habitación", 1, 4, key="ho_n")
        with st.form("ho_form", border=False):
            nom_col, ciu_col = st.columns(2)
            nombre = nom_col.text_input("Nombre del hotel", key="ho_nombre")
            ciudad_h = ciu_col.selectbox("Ciudad del hotel", iatas, index=None, format_func=ciudad, key="ho_ciudad",
                                         placeholder="Elige la ciudad")
            dir_col, est_col = st.columns([3, 1])
            direccion = dir_col.text_input("Dirección", key="ho_direccion")
            estrellas = est_col.selectbox("Estrellas", [1, 2, 3, 4, 5], index=None, key="ho_estrellas",
                                          format_func=lambda n: "★" * n, placeholder="Elige")
            servicios = st.text_input("Servicios (separados por comas)", key="ho_servicios",
                                      placeholder="Ej.: wifi, piscina, desayuno")
            habitaciones = []
            for i in range(n_hab):
                tip, cap, pre, can = st.columns(4)
                habitaciones.append(sin_vacios({
                    "tipo": tip.selectbox(f"Habitación {i + 1}", TIPOS_HAB, index=i, key=f"ho_h{i}_tipo"),
                    "capacidad": cap.number_input("Capacidad (personas)", min_value=1, step=1, value=None,
                                                  key=f"ho_h{i}_capacidad"),
                    "precio_noche": pre.number_input("Precio por noche", min_value=0, step=10000, value=None,
                                                     key=f"ho_h{i}_precio"),
                    "cantidad": can.number_input("Cantidad de habitaciones", min_value=0, step=1, value=None,
                                                 key=f"ho_h{i}_cantidad")}))
            enviar = st.form_submit_button("Registrar hotel", type="primary", icon=":material/check:")
        if enviar:
            tipos = [h["tipo"] for h in habitaciones]
            if len(set(tipos)) != len(tipos):
                st.warning("Cada tipo de habitación debe aparecer una sola vez.")
            else:
                try:
                    hotel = schemas.HotelCreate(**sin_vacios({"nombre": nombre, "ciudad": ciudad_h, "direccion": direccion,
                                                              "estrellas": estrellas, "servicios": lista_texto(servicios),
                                                              "habitaciones": habitaciones}))
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    registrar(lambda: api_client.crear_hotel(hotel.model_dump(mode="json", exclude_none=True)),
                              pestana="hoteles", prefijo="ho_", que="el hotel",
                              exito=lambda h: f"Se registró el hotel «{h['nombre']}». Para que tenga disponibilidad, "
                                              "genera sus noches en «Generar noches».")

    with st.expander("Generar noches", icon=":material/calendar_month:", key="exp_noches"):
        st.caption("Crea el inventario de noches de un hotel. Las noches que ya existen no se modifican: "
                   "conservan sus cupos y lo ya vendido.")
        hotel_n = st.selectbox("Hotel", hoteles or [], index=None, key="no_hotel", placeholder="Elige el hotel",
                               format_func=lambda h: f"{h['nombre']} · {ciudad(h['ciudad'])}")
        des_col, has_col = st.columns(2)
        desde_n = des_col.date_input("Desde (primera noche)", value=None, min_value=HOY, format="DD/MM/YYYY",
                                     key="no_desde")
        hasta_n = has_col.date_input("Hasta (día de salida, sin esa noche)", value=None, min_value=HOY,
                                     format="DD/MM/YYYY", key="no_hasta")
        todos = [x["tipo"] for x in hotel_n["habitaciones"]] if hotel_n else []
        tipos_n = st.multiselect("Tipos de habitación", todos, default=todos,
                                 key=f"no_tipos_{hotel_n['id'] if hotel_n else ''}")
        if desde_n and hasta_n and hasta_n > desde_n:
            st.caption(f"Noches del {desde_n:%d/%m/%Y} al {hasta_n - timedelta(days=1):%d/%m/%Y}: "
                       f"{(hasta_n - desde_n).days} por cada tipo elegido.")
        if st.button("Generar noches", type="primary", icon=":material/check:", key="no_generar"):
            if not hotel_n:
                st.warning("Elige el hotel.")
            elif not tipos_n:
                st.warning("Elige al menos un tipo de habitación.")
            elif not (desde_n and hasta_n):
                st.warning("Elige las fechas desde y hasta.")
            elif hasta_n <= desde_n:
                st.warning("La fecha hasta debe ser posterior a la fecha desde.")
            else:
                try:
                    pedido = schemas.NochesGenerar(desde=desde_n, hasta=hasta_n,
                                                   tipos=None if set(tipos_n) == set(todos) else tipos_n)
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    try:
                        r = api_client.generar_noches(hotel_n["id"], pedido.model_dump(mode="json", exclude_none=True))
                    except requests.RequestException:
                        st.error("No hay conexión con la API: no se generaron las noches. Inténtalo de nuevo.")
                    else:
                        if r.status_code == 201:
                            res = r.json()
                            st.success(f"Noches de {hotel_n['nombre']}: {res['creadas']} creadas y "
                                       f"{res['existentes']} que ya existían.", icon=":material/check_circle:")
                            st.caption("Las noches que ya existían no se tocaron: conservan sus cupos y ventas.")
                        else:
                            st.error(f"No se pudieron generar las noches: {api_client.detalle_error(r)}",
                                     icon=":material/error:")

# ─────────────────────────────── Tours ───────────────────────────────
with t_tours:
    aviso("tours")
    encabezado_tab("Tours", "Un tour se vende por sus salidas: cada una con fecha, precio por persona y cupos.")
    tours = leer("listar_tours")
    if not sin_lista(tours, "tours"):
        st.table([{"Tour": t["nombre"], "Ciudad": ciudad(t["ciudad"]),
                   "Duración": f"{t['horas']:g} h" if t.get("horas") is not None else "—",
                   "Incluye": ", ".join(t["incluye"]) or "—",
                   "Encuentro": (t.get("encuentro") or {}).get("lugar", "—"),
                   "Salidas próximas": len(leer("listar_salidas", t["id"]) or [])} for t in tours], hide_index=True)

    with st.expander("Registrar tour", icon=":material/add:", key="exp_tour"):
        st.info("Un tour nuevo necesita al menos una salida para ser vendible.", icon=":material/info:")
        with st.form("to_form", border=False):
            nom_col, ciu_col, hor_col = st.columns([3, 2, 1])
            nombre = nom_col.text_input("Nombre del tour", key="to_nombre")
            ciudad_t = ciu_col.selectbox("Ciudad del tour (opcional)", iatas, index=None, format_func=ciudad,
                                         key="to_ciudad", placeholder="Sin ciudad",
                                         help="Sin ciudad, el tour no se puede incluir en una reserva.")
            horas = hor_col.number_input("Duración (horas)", min_value=0.0, step=0.5, value=None, key="to_horas")
            descripcion = st.text_area("Descripción (opcional)", key="to_descripcion", height=80)
            inc_col, enc_col = st.columns(2)
            incluye = inc_col.text_input("Incluye (separado por comas)", key="to_incluye",
                                         placeholder="Ej.: guía bilingüe, almuerzo")
            lugar = enc_col.text_input("Lugar de encuentro (opcional)", key="to_lugar")
            enviar = st.form_submit_button("Registrar tour", type="primary", icon=":material/check:")
        if enviar:
            try:
                tour = schemas.TourCreate(**sin_vacios({
                    "nombre": nombre, "ciudad": ciudad_t, "descripcion": descripcion.strip() or None, "horas": horas,
                    "incluye": lista_texto(incluye), "encuentro": {"lugar": lugar.strip()} if lugar.strip() else None}))
            except ValidationError as e:
                st.warning(aviso_validacion(e))
            else:
                registrar(lambda: api_client.crear_tour(tour.model_dump(mode="json", exclude_none=True)),
                          pestana="tours", prefijo="to_", que="el tour",
                          exito=lambda t: f"Se registró el tour «{t['nombre']}». Agrégale al menos una salida en "
                                          "«Agregar salida» para poder venderlo.")

    with st.expander("Agregar salida", icon=":material/event:", key="exp_salida"):
        tour_s = st.selectbox("Tour", tours or [], index=None, key="sa_tour", placeholder="Elige el tour",
                              format_func=lambda t: f"{t['nombre']} · {ciudad(t['ciudad'])}")
        if tour_s:
            salidas = leer("listar_salidas", tour_s["id"])
            if salidas:
                st.caption("Salidas próximas de este tour (hora de Bogotá):")
                st.table([{"Fecha": hora_bogota(s["fecha"]), "Precio por persona": pesos(s["precio"], markdown=True),
                           "Cupos": s["cupos"], "Libres": s["libres"]} for s in salidas], hide_index=True)
            else:
                st.caption("Este tour aún no tiene salidas próximas.")
        with st.form("sa_form", border=False):
            fec, hor, pre, cup = st.columns(4)
            fecha_s = con_hora(fec.date_input("Fecha de la salida", value=None, min_value=HOY, format="DD/MM/YYYY",
                                              key="sa_f_dia"),
                               hor.time_input("Hora de la salida", value=None, step=300, key="sa_f_hora"))
            precio_s = pre.number_input("Precio por persona", min_value=0, step=10000, value=None, key="sa_f_precio")
            cupos_s = cup.number_input("Cupos", min_value=0, step=1, value=None, key="sa_f_cupos")
            st.caption("Fecha y hora en hora de Bogotá.")
            enviar = st.form_submit_button("Agregar salida", type="primary", icon=":material/check:")
        if enviar:
            if not tour_s:
                st.warning("Elige el tour.")
            elif fecha_s is None:
                st.warning("Escribe la fecha y la hora de la salida.")
            else:
                try:
                    salida = schemas.SalidaCreate(**sin_vacios({"tour_id": tour_s["id"], "fecha": fecha_s,
                                                                "precio": precio_s, "cupos": cupos_s}))
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    registrar(lambda: api_client.crear_salida(tour_s["id"], salida.model_dump(mode="json")),
                              pestana="tours", prefijo="sa_f_", que="la salida",
                              exito=lambda s: f"Salida del {hora_bogota(s['fecha'])} agregada al tour «{tour_s['nombre']}».",
                              pista_duplicado="Ese tour ya tiene una salida en esa misma fecha y hora.")

# ─────────────────────────────── Paquetes ───────────────────────────────
with t_paquetes:
    aviso("paquetes")
    encabezado_tab("Paquetes", "Precio por persona con el descuento, calculado con los precios copiados al crearlo.")
    paquetes = leer("listar_paquetes", False)

    def estado_venta(p: dict) -> str:
        desde, hasta = date.fromisoformat(p["desde"][:10]), date.fromisoformat(p["hasta"][:10])
        return "Aún no inicia" if HOY < desde else "Cerrada" if HOY > hasta else "En venta"

    if not sin_lista(paquetes, "paquetes"):
        st.table([{"Paquete": p["nombre"], "Destino": ciudad(p["destino"]), "Descuento": f"{p['descuento']:g} %",
                   "Venta": f"{fecha_dia(p['desde'])} al {fecha_dia(p['hasta'])}", "Estado de venta": estado_venta(p),
                   "Componentes": " · ".join(c["nombre"] for c in p["componentes"]),
                   "Precio por persona": pesos(precio_paquete(p["componentes"], p["descuento"]), markdown=True)}
                  for p in paquetes], hide_index=True)

    with st.expander("Registrar paquete", icon=":material/add:", key="exp_paquete"):
        st.session_state.setdefault("pq_componentes", [])
        nom_col, des_col, dto_col = st.columns([3, 2, 1])
        nombre_p = nom_col.text_input("Nombre del paquete", key="pq_nombre")
        destino_p = des_col.selectbox("Destino del paquete", iatas, index=None, format_func=ciudad, key="pq_destino",
                                      placeholder="Elige la ciudad")
        descuento = dto_col.number_input("Descuento (%)", 0, 100, key="pq_descuento")
        vd_col, vh_col = st.columns(2)
        venta_desde = vd_col.date_input("Venta desde", value=None, format="DD/MM/YYYY", key="pq_desde")
        venta_hasta = vh_col.date_input("Venta hasta", value=None, format="DD/MM/YYYY", key="pq_hasta",
                                        help="La venta debe cerrar a más tardar el día anterior al viaje.")

        st.markdown("##### Componentes")
        tipo_c = st.radio("Tipo de componente", ["Vuelo", "Hotel", "Tour"], horizontal=True, key="pq_tipo")
        nuevo = None            # componente listo para agregar: cuerpo para la API + nombre, precio y fecha de inicio
        if tipo_c == "Vuelo":
            vu_col, ta_col = st.columns([3, 2])
            vuelo_p = vu_col.selectbox("Vuelo del paquete", [v for v in vuelos or [] if not ya_paso(v["sale"])],
                                       index=None, key="pq_vuelo", placeholder="Elige el vuelo",
                                       format_func=lambda v: f"{v['codigo']} · {v['origen']} → {v['destino']} · "
                                                             f"{hora_bogota(v['sale'])}")
            if vuelo_p:
                tarifa_p = ta_col.selectbox("Tarifa del vuelo", vuelo_p["tarifas"], key=f"pq_tarifa_{vuelo_p['id']}",
                                            format_func=lambda t: f"{TARIFAS[t['nombre']]} · {pesos(t['precio'])}")
                nuevo = {"cuerpo": {"tipo": "vuelo", "ref_id": vuelo_p["id"], "detalle": {"tarifa": tarifa_p["nombre"]}},
                         "nombre": f"Vuelo: {vuelo_p['origen']}-{vuelo_p['destino']} {vuelo_p['codigo']} · "
                                   f"{TARIFAS[tarifa_p['nombre']]}",
                         "precio": tarifa_p["precio"], "inicio": vuelo_p["sale"]}
        elif tipo_c == "Hotel":
            ho_col, ti_col, no_col, en_col = st.columns([3, 2, 1, 2])
            hotel_p = ho_col.selectbox("Hotel del paquete", hoteles or [], index=None, key="pq_hotel",
                                       placeholder="Elige el hotel",
                                       format_func=lambda h: f"{h['nombre']} · {ciudad(h['ciudad'])}")
            noches_p = no_col.number_input("Noches", 1, 60, key="pq_noches")
            entrada_p = en_col.date_input("Fecha de entrada", value=None, min_value=HOY, format="DD/MM/YYYY",
                                          key="pq_entrada")
            if hotel_p:
                hab_p = ti_col.selectbox("Tipo de habitación", hotel_p["habitaciones"], key=f"pq_hab_{hotel_p['id']}",
                                         format_func=lambda x: f"{x['tipo']} · {pesos(x['precio_noche'])} por noche")
                if entrada_p:
                    nuevo = {"cuerpo": {"tipo": "hotel", "ref_id": hotel_p["id"],
                                        "detalle": {"tipo_hab": hab_p["tipo"], "noches": noches_p,
                                                    "entrada": entrada_p.isoformat()}},
                             "nombre": f"Hotel: {hotel_p['nombre']} · {hab_p['tipo']} · {noches_p} noche(s) desde el "
                                       f"{entrada_p:%d/%m/%Y}",
                             # Por persona: precio por noche × noches, sin multiplicar por habitaciones
                             "precio": hab_p["precio_noche"] * noches_p,
                             "inicio": f"{entrada_p.isoformat()}T00:00:00+00:00"}
        else:
            tu_col, sa_col = st.columns(2)
            tour_p = tu_col.selectbox("Tour del paquete", tours or [], index=None, key="pq_tour",
                                      placeholder="Elige el tour",
                                      format_func=lambda t: f"{t['nombre']} · {ciudad(t['ciudad'])}")
            if tour_p:
                salidas_p = leer("listar_salidas", tour_p["id"]) or []
                if not salidas_p:
                    sa_col.caption("Este tour no tiene salidas próximas.")
                else:
                    salida_p = sa_col.selectbox("Salida del tour", salidas_p, key=f"pq_salida_{tour_p['id']}",
                                                format_func=lambda s: f"{hora_bogota(s['fecha'])} · {pesos(s['precio'])}")
                    nuevo = {"cuerpo": {"tipo": "tour", "ref_id": tour_p["id"], "detalle": {"salida_id": salida_p["id"]}},
                             "nombre": f"Tour: {tour_p['nombre']} · {hora_bogota(salida_p['fecha'])}",
                             "precio": salida_p["precio"], "inicio": salida_p["fecha"]}
        precio_col, boton_col = st.columns([3, 1], vertical_alignment="center")
        if nuevo:
            precio_col.caption(f"Precio por persona de este componente: {pesos(nuevo['precio'], markdown=True)}")
        boton_col.button("Agregar componente", icon=":material/add:", disabled=nuevo is None, key="pq_agregar",
                         on_click=agregar_componente, args=(nuevo,))

        componentes = st.session_state.pq_componentes
        with st.container(border=True, key="tarjeta_estimado"):
            if not componentes:
                st.caption("Aún no hay componentes. Agrega al menos uno.")
            for c in componentes:
                texto, quitar = st.columns([5, 1], vertical_alignment="center")
                texto.markdown(f"{c['nombre']}  \n:gray[Por persona:] **{pesos(c['precio'], markdown=True)}**")
                quitar.button("Quitar", icon=":material/delete:", type="tertiary", key=f"pq_quitar_{c['id']}",
                              on_click=quitar_componente, args=(c["id"],))
            st.divider()
            suma = sum(c["precio"] for c in componentes)
            st.metric("Precio estimado por persona", pesos(precio_paquete(componentes, descuento)))
            st.caption(f"Suma de componentes {pesos(suma, markdown=True)} menos {descuento} % de descuento. Es un "
                       "estimado con los precios actuales del catálogo: el precio definitivo lo calcula el sistema "
                       "al registrar el paquete.")
            if componentes:
                # Regla del servidor: la venta cierra a más tardar el día anterior al primer componente (en UTC)
                ultimo = (min(datetime.fromisoformat(c["inicio"]) for c in componentes).astimezone(timezone.utc)
                          - timedelta(days=1)).date()
                st.caption(f"Con estos componentes, la venta puede cerrar (venta hasta) a más tardar el "
                           f"{ultimo:%d/%m/%Y}.")

        if st.button("Registrar paquete", type="primary", icon=":material/check:", key="pq_registrar"):
            if not componentes:
                st.warning("Agrega al menos un componente al paquete.")
            elif venta_desde and venta_hasta and venta_hasta < venta_desde:
                st.warning("La fecha «venta hasta» no puede ser anterior a «venta desde».")
            else:
                try:
                    paquete = schemas.PaqueteCreate(**sin_vacios({
                        "nombre": nombre_p, "destino": destino_p, "descuento": descuento, "desde": venta_desde,
                        "hasta": venta_hasta, "componentes": [c["cuerpo"] for c in componentes]}))
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    registrar(lambda: api_client.crear_paquete(paquete.model_dump(mode="json")),
                              pestana="paquetes", prefijo="pq_", que="el paquete",
                              exito=lambda p: f"Se registró el paquete «{p['nombre']}». Precio por persona calculado por el "
                                              f"sistema: {pesos(precio_paquete(p['componentes'], p['descuento']), markdown=True)}.")

# ─────────────────────────────── Clientes ───────────────────────────────
with t_clientes:
    aviso("clientes")
    encabezado_tab("Clientes", "Clientes registrados, por nombre. El tipo y el número de documento identifican a "
                               "cada cliente.")
    clientes = leer("listar_clientes")
    if not sin_lista(clientes, "clientes"):
        st.table([{"Tipo": tipo_doc(c["tipo"]), "Documento": c["documento"], "Nombre o razón social": c["nombre"],
                   "Correo": c["correo"], "Teléfono": c["telefono"]} for c in clientes], hide_index=True)

    with st.expander("Registrar cliente", icon=":material/person_add:", key="exp_cliente"):
        with st.form("cl_form", border=False):
            tip_col, doc_col, nom_col = st.columns([2, 2, 3])
            tipo_cl = tip_col.selectbox("Tipo de documento", TIPOS_DOCUMENTO, index=None, format_func=NOMBRES_TIPO.get,
                                        key="cl_tipo", placeholder="Elige el tipo")
            documento = doc_col.text_input("Número de documento", key="cl_documento", help=REGLAS_DOCUMENTO)
            nombre = nom_col.text_input("Nombre o razón social", key="cl_nombre")
            cor_col, tel_col = st.columns(2)
            correo = cor_col.text_input("Correo", key="cl_correo")
            telefono = tel_col.text_input("Teléfono", key="cl_telefono")
            enviar = st.form_submit_button("Registrar cliente", type="primary", icon=":material/check:")
        if enviar:
            if tipo_cl is None:
                st.warning("Revisa los datos. Elige el tipo de documento.")
            else:
                try:
                    # El DTO del backend aplica la misma regla del documento según el tipo
                    cliente = schemas.ClienteCreate(tipo=tipo_cl, documento=documento, nombre=nombre, correo=correo,
                                                    telefono=telefono)
                except ValidationError as e:
                    st.warning(aviso_validacion(e))
                else:
                    registrar(lambda: api_client.crear_cliente(cliente.model_dump(mode="json", exclude_none=True)),
                              pestana="clientes", prefijo="cl_", que="el cliente",
                              exito=lambda c: f"Se registró a {c['nombre']} (documento {documento_cliente(c)}) como cliente.",
                              pista_duplicado="Ya hay un cliente registrado con ese documento.")
