"""front/pages/01_Buscar_y_reservar.py — Catálogo con disponibilidad real y registro de reservas."""
import os
import sys
import uuid
from datetime import date, datetime, timezone

import requests
import streamlit as st
from pydantic import ValidationError

import api_client
from estilo import (NOMBRES_TIPO, REGLAS_DOCUMENTO, RESERVAS, TIPOS_DOCUMENTO, aplicar_estilo, documento_cliente,
                    encabezado_modulo, hora_bogota, pesos, requerir_asesor, tipo_doc)

# Mismos DTO del backend para pre-validar antes de tocar la red
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from back.app import schemas  # noqa: E402

st.set_page_config(page_title="Buscar y reservar · Brújula Viajes", page_icon="assets/logo_isotipo.png",
                   layout="wide")
aplicar_estilo()
asesor = requerir_asesor()
encabezado_modulo("Buscar y reservar",
                  "Consulta el catálogo con disponibilidad real y registra la reserva del cliente.")

if not api_client.api_en_linea():
    st.warning("No hay conexión con la API. Levántala desde back/ con `uvicorn main:app --reload` "
               "y recarga la página.", icon=":material/cloud_off:")
    st.stop()

st.session_state.setdefault("reserva", [])        # reserva en curso: lista de ítems
st.session_state.setdefault("cliente", None)

TARIFAS = {"Basica": "Básica", "Clasica": "Clásica", "Flexible": "Flexible"}
TIPOS_HAB = ["Sencilla", "Doble", "Familiar", "Suite"]
CAMPOS = {"documento": "el documento", "nombre": "el nombre o razón social", "correo": "el correo",
          "telefono": "el teléfono", "nacimiento": "la fecha de nacimiento"}
HOY = date.today()


@st.cache_data(ttl=20, show_spinner=False)
def leer(ruta: str, **params):
    """GET de solo lectura con caché corta. None si la API no responde o rechaza la consulta.
    La caché se limpia al registrar una reserva o un cliente, para ver el inventario nuevo."""
    try:
        r = api_client.get(ruta, **{k: v for k, v in params.items() if v is not None})
    except requests.RequestException:
        return None
    return r.json() if r.status_code == 200 else None


def aviso_validacion(e: ValidationError) -> str:
    """Primer error de Pydantic en una línea en español, con el campo y el pasajero si aplica."""
    error = e.errors()[0]
    loc = error["loc"]          # vacío en las reglas de todo el modelo (documento según su tipo)
    campo = CAMPOS.get(str(loc[-1]), str(loc[-1])) if loc else ""
    quien = f"Pasajero {loc[1] + 1}: " if loc and loc[0] == "pasajeros" and len(loc) > 2 else ""
    tipo, ctx = error["type"], error.get("ctx", {})
    if tipo == "missing" or (tipo == "string_too_short" and ctx.get("min_length") == 1):
        detalle = f"falta {campo}"
    elif tipo == "string_too_short":
        detalle = f"{campo} debe tener al menos {ctx['min_length']} caracteres"
    elif tipo == "string_too_long":
        detalle = f"{campo} admite máximo {ctx['max_length']} caracteres"
    elif tipo.startswith("date"):
        detalle = f"falta {campo} o no es válida"
    elif campo == "el correo":
        detalle = "el correo no tiene un formato válido"
    else:
        detalle = error["msg"].removeprefix("Value error, ")
    return f"Revisa los datos. {quien}{detalle[0].upper()}{detalle[1:]}."


def buscar_exacto(numero: str, tipo: str | None) -> dict:
    """Búsqueda exacta por tipo + número. {"cliente": ...} si lo encuentra; si no, el aviso o error que
    se muestra. Sin tipo, un número que está en dos tipos da 409: la API no escoge uno al azar."""
    if not numero:
        return {"aviso": "Escribe el número de documento.", "icono": ":material/edit:"}
    try:
        r = api_client.buscar_cliente(numero, tipo)
    except requests.RequestException:
        return {"error": "No hay conexión con la API. Inténtalo de nuevo en un momento."}
    if r.status_code == 200:
        return {"cliente": r.json()}
    if r.status_code == 404:
        return {"aviso": f"No hay un cliente {tipo} con el número {numero}." if tipo else
                f"No hay clientes con el número {numero}.", "icono": ":material/search_off:"}
    if r.status_code == 409:
        return {"aviso": f"{api_client.detalle_error(r)} Elige en «Tipo de documento» si es CC, CE, NIT o "
                         "Pasaporte y busca de nuevo.", "icono": ":material/rule:"}
    return {"error": f"No se pudo buscar el cliente: {api_client.detalle_error(r)}"}


def agregar(item: dict, descripcion: str, estimado: int):
    if len(st.session_state.reserva) >= 20:
        st.warning("Una reserva admite máximo 20 productos.")
        return
    st.session_state.reserva.append({"id": uuid.uuid4().hex, "item": item,
                                     "descripcion": descripcion, "estimado": estimado})
    st.toast(f"Agregado a la reserva en curso: {descripcion}", icon=":material/add_shopping_cart:")


def encabezado_tab(icono: str, titulo: str, nota: str):
    imagen, texto = st.columns([1, 10], vertical_alignment="center")
    imagen.image(f"assets/{icono}", width=64)
    texto.subheader(titulo)
    texto.caption(nota)


def fecha_dia(iso: str) -> str:
    """Fechas de día (noches, vigencias) llegan como 00:00 UTC: se muestra el día tal cual."""
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def ya_paso(iso: str) -> bool:
    return datetime.fromisoformat(iso) <= datetime.now(timezone.utc)


def panel_exito(res: dict):
    with st.container(border=True, key="tarjeta_exito"):
        st.success(f"Reserva **{res['codigo']}** registrada para {res['cliente']['nombre']}. "
                   f"Estado: **{res['estado']}**.", icon=":material/check_circle:")
        st.dataframe([{"Producto": i["nombre"], "Tipo": i["tipo"].capitalize(), "Ciudad": i["ciudad"],
                       "Cantidad": i["cantidad"], "Precio": pesos(i["precio"]),
                       "Subtotal": pesos(i["subtotal"])} for i in res["items"]],
                     hide_index=True, width="stretch")
        total, pagado, saldo = st.columns(3)
        total.metric("Total", pesos(res["total"]))
        pagado.metric("Pagado", pesos(res["pagado"]))
        saldo.metric("Saldo", pesos(res["saldo"]))
        enlace, otra = st.columns([1, 1], vertical_alignment="center")
        enlace.page_link(RESERVAS, label="Ver en Reservas: pagos y cancelaciones", icon=":material/arrow_forward:")
        if otra.button("Registrar otra reserva", icon=":material/add:"):
            del st.session_state["resultado"]
            st.rerun()


# ─────────────────────────────── 1. Catálogo y reserva en curso ───────────────────────────────
ciudades = leer("/ciudades/") or []
nombres = {c["iata"]: c["nombre"] for c in ciudades}
# Una sola fila: a la izquierda todo el flujo (catálogo, cliente, pasajeros) y a la derecha el
# resumen de la reserva en curso, que queda pegado arriba mientras se baja (ver estilo.py).
flujo, resumen = st.columns([7, 3], gap="large")
filtro, _ = flujo.columns([1, 2])
destino = filtro.selectbox("Ciudad destino", ["Todas", *nombres], key="f_destino",
                           format_func=lambda x: "Todas las ciudades" if x == "Todas" else f"{nombres[x]} ({x})")
destino = None if destino == "Todas" else destino

with flujo:
    t_vuelos, t_hoteles, t_tours, t_paquetes = st.tabs(
        [":material/flight: Vuelos", ":material/hotel: Hoteles", ":material/hiking: Tours",
         ":material/luggage: Paquetes"])

    with t_vuelos:
        encabezado_tab("icono_vuelos.png", "Vuelos", "Precio por silla. Los libres son el inventario actual.")
        origen_col, fecha_col = st.columns(2)
        origen = origen_col.selectbox("Origen", ["Todos", *nombres], key="f_origen",
                                      format_func=lambda x: "Todos los orígenes" if x == "Todos" else f"{nombres[x]} ({x})")
        dia = fecha_col.date_input("Fecha de salida (opcional)", value=None, min_value=HOY,
                                   format="DD/MM/YYYY", key="f_fecha")
        vuelos = leer("/vuelos/", origen=None if origen == "Todos" else origen, destino=destino,
                      fecha=dia.isoformat() if dia else None)
        if vuelos is None:
            st.warning("No se pudo consultar los vuelos.")
        elif not vuelos:
            st.info("No hay vuelos con esos filtros.")
        for v in vuelos or []:
            with st.container(border=True, key=f"panel_vuelo_{v['id']}"):
                info, accion = st.columns([3, 2], gap="medium")
                info.markdown(f"**{v['origen']} → {v['destino']}** · {v['codigo']} · {v['aerolinea']}")
                info.caption(f"Sale {hora_bogota(v['sale'])} · Llega {hora_bogota(v['llega'])} (hora de Bogotá)")
                info.markdown("  \n".join(f"{TARIFAS[t['nombre']]}: **{pesos(t['precio'], markdown=True)}** · "
                                          f"{t['libres']} libres · {t['equipaje']}" for t in v["tarifas"]))
                con_cupo = [t for t in v["tarifas"] if t["libres"] > 0]
                if ya_paso(v["sale"]) or not con_cupo:
                    accion.caption("Este vuelo ya salió." if ya_paso(v["sale"]) else "Sin sillas libres.")
                    continue
                tarifa = accion.selectbox("Tarifa", con_cupo, key=f"tarifa_{v['id']}",
                                          format_func=lambda t: f"{TARIFAS[t['nombre']]} · {pesos(t['precio'])}")
                sillas = accion.number_input("Sillas", 1, tarifa["libres"],
                                             key=f"sillas_{v['id']}_{tarifa['nombre']}")
                if accion.button("Agregar", icon=":material/add:", key=f"agregar_{v['id']}"):
                    agregar({"tipo": "vuelo", "ref_id": v["id"], "tarifa": tarifa["nombre"], "cantidad": sillas},
                            f"Vuelo {v['codigo']} {v['origen']}→{v['destino']} · {TARIFAS[tarifa['nombre']]} · "
                            f"{sillas} silla(s)", sillas * tarifa["precio"])

    with t_hoteles:
        encabezado_tab("icono_hoteles.png", "Hoteles",
                       "Elige fechas, tipo de habitación y personas para consultar la disponibilidad.")
        e_col, s_col, t_col, p_col = st.columns([3, 3, 2, 2])
        entrada = e_col.date_input("Entrada", value=None, min_value=HOY, format="DD/MM/YYYY", key="f_entrada")
        salida = s_col.date_input("Salida", value=None, min_value=HOY, format="DD/MM/YYYY", key="f_salida")
        tipo = t_col.selectbox("Tipo de habitación", TIPOS_HAB, key="f_tipo")
        personas = p_col.number_input("Personas", 1, 20, key="f_personas")
        fechas_ok = bool(entrada and salida and salida > entrada)
        if entrada and salida and not fechas_ok:
            st.warning("La salida debe ser posterior a la entrada.")
        elif not fechas_ok:
            st.caption("Sin fechas solo se muestran las tarifas; con entrada y salida se consulta la disponibilidad.")
        hoteles = leer("/hoteles/", ciudad=destino)
        if hoteles is None:
            st.warning("No se pudo consultar los hoteles.")
        elif not hoteles:
            st.info("No hay hoteles en esa ciudad.")
        for h in hoteles or []:
            with st.container(border=True, key=f"panel_hotel_{h['id']}"):
                info, accion = st.columns([3, 2], gap="medium")
                info.markdown(f"**{h['nombre']}** · {'★' * h['estrellas']} · {nombres.get(h['ciudad'], h['ciudad'])}")
                info.caption(h["direccion"] + (f" · {', '.join(h['servicios'])}" if h["servicios"] else ""))
                info.markdown("  \n".join(f"{x['tipo']} (hasta {x['capacidad']} persona{'s' if x['capacidad'] > 1 else ''}): "
                                          f"**{pesos(x['precio_noche'], markdown=True)}** por noche" for x in h["habitaciones"]))
                hab = next((x for x in h["habitaciones"] if x["tipo"] == tipo), None)
                if not hab:
                    accion.caption(f"No maneja habitaciones {tipo}.")
                    continue
                if not fechas_ok:
                    continue
                disp = leer(f"/hoteles/{h['id']}/disponibilidad", tipo=tipo, entrada=entrada.isoformat(),
                            salida=salida.isoformat(), personas=personas)
                if disp is None:
                    accion.warning("No se pudo consultar la disponibilidad.")
                elif not disp["disponible"]:
                    noches = ", ".join(fecha_dia(f) for f in disp.get("faltan", []))
                    accion.warning(f"Sin disponibilidad: no hay cupo la(s) noche(s) del {noches}." if noches
                                   else "Sin disponibilidad en esas fechas.", icon=":material/event_busy:")
                else:
                    accion.badge(f"Disponible · {disp['habitaciones']} hab. · {disp['noches']} noche(s)",
                                 icon=":material/event_available:", color="green")
                    if accion.button("Agregar", icon=":material/add:", key=f"agregar_{h['id']}"):
                        agregar({"tipo": "hotel", "ref_id": h["id"], "tipo_hab": tipo, "entrada": entrada.isoformat(),
                                 "salida": salida.isoformat(), "cantidad": personas},
                                f"{h['nombre']} · {tipo} · {entrada:%d/%m} a {salida:%d/%m} · {personas} persona(s)",
                                personas * hab["precio_noche"] * disp["noches"])

    with t_tours:
        encabezado_tab("icono_tours.png", "Tours", "Precio por persona en cada salida programada.")
        tours = leer("/tours/", ciudad=destino)
        if tours is None:
            st.warning("No se pudo consultar los tours.")
        elif not tours:
            st.info("No hay tours en esa ciudad.")
        for t in tours or []:
            with st.container(border=True, key=f"panel_tour_{t['id']}"):
                info, accion = st.columns([3, 2], gap="medium")
                duracion = f" · {t['horas']:g} horas" if t.get("horas") else ""
                info.markdown(f"**{t['nombre']}** · {nombres.get(t['ciudad'], t['ciudad'] or 'Sin ciudad')}{duracion}")
                if t.get("descripcion"):
                    info.write(t["descripcion"])
                if t["incluye"]:
                    info.caption("Incluye: " + ", ".join(t["incluye"]))
                salidas = [s for s in leer(f"/tours/{t['id']}/salidas") or [] if s["libres"] > 0]
                if not salidas:
                    accion.caption("Sin salidas con cupo.")
                    continue
                s = accion.selectbox("Salida", salidas, key=f"salida_{t['id']}",
                                     format_func=lambda s: f"{hora_bogota(s['fecha'])} · {pesos(s['precio'])} · "
                                                           f"{s['libres']} libres")
                cupos = accion.number_input("Cupos", 1, s["libres"], key=f"cupos_{t['id']}_{s['id']}")
                if accion.button("Agregar", icon=":material/add:", key=f"agregar_{t['id']}"):
                    agregar({"tipo": "tour", "ref_id": t["id"], "salida_id": s["id"], "cantidad": cupos},
                            f"Tour {t['nombre']} · {hora_bogota(s['fecha'])} · {cupos} cupo(s)", cupos * s["precio"])

    with t_paquetes:
        encabezado_tab("icono_paquetes.png", "Paquetes",
                       "Precio por persona con el descuento del paquete. Solo se muestran los vigentes.")
        paquetes = leer("/paquetes/", destino=destino)
        if paquetes is None:
            st.warning("No se pudo consultar los paquetes.")
        elif not paquetes:
            st.info("No hay paquetes vigentes para esa ciudad.")
        todos_vuelos = {v["id"]: v for v in leer("/vuelos/", limite=200) or []}
        for p in paquetes or []:
            with st.container(border=True, key=f"panel_paquete_{p['id']}"):
                info, accion = st.columns([3, 2], gap="medium")
                info.markdown(f"**{p['nombre']}** · {nombres.get(p['destino'], p['destino'])}")
                info.caption(f"A la venta del {fecha_dia(p['desde'])} al {fecha_dia(p['hasta'])}")
                info.markdown("  \n".join(f"{c['tipo'].capitalize()}: {c['nombre']} · {pesos(c['precio'], markdown=True)}"
                                          for c in p["componentes"]))
                precio = round(sum(c["precio"] for c in p["componentes"]) * (1 - p["descuento"] / 100))
                accion.markdown(f"**{pesos(precio, markdown=True)}** por persona  \nIncluye {p['descuento']:g} % de descuento")
                # Cupo: lo que permitan las sillas y los cupos de sus componentes. El hotel lo verifica la API.
                libres = []
                for c in p["componentes"]:
                    if c["tipo"] == "vuelo" and c["ref_id"] in todos_vuelos:
                        libres += [t["libres"] for t in todos_vuelos[c["ref_id"]]["tarifas"]
                                   if t["nombre"] == c["detalle"]["tarifa"]]
                    elif c["tipo"] == "tour":
                        libres += [s["libres"] for s in leer(f"/tours/{c['ref_id']}/salidas") or []
                                   if s["id"] == c["detalle"]["salida_id"]]
                cupo = min(libres, default=20)
                if cupo < 1:
                    accion.caption("Sin cupo en alguno de sus componentes.")
                    continue
                n = accion.number_input("Personas", 1, min(cupo, 20), key=f"personas_{p['id']}")
                if any(c["tipo"] == "hotel" for c in p["componentes"]):
                    accion.caption("Disponibilidad final del paquete sujeta a validación al registrar.")
                if accion.button("Agregar", icon=":material/add:", key=f"agregar_{p['id']}"):
                    agregar({"tipo": "paquete", "ref_id": p["id"], "cantidad": n},
                            f"Paquete {p['nombre']} · {n} persona(s)", n * precio)

# height="stretch": el envoltorio del panel ocupa el alto de la columna, así el sticky tiene recorrido
with resumen, st.container(key="resumen_panel", height="stretch"), st.container(border=True, key="tarjeta_reserva"):
    st.markdown("#### :primary[:material/shopping_bag:] Reserva en curso")
    reserva = st.session_state.reserva
    if not reserva:
        st.caption("Aún no hay productos. Agrégalos desde el catálogo.")
    for it in reserva:
        st.markdown(f"{it['descripcion']}  \nEstimado: **{pesos(it['estimado'], markdown=True)}**")
        if st.button("Quitar", icon=":material/delete:", type="tertiary", key=f"quitar_{it['id']}"):
            st.session_state.reserva = [x for x in reserva if x["id"] != it["id"]]
            st.rerun()
    if reserva:
        st.divider()
        st.markdown(f"**Total estimado: {pesos(sum(x['estimado'] for x in reserva), markdown=True)}**")
        st.caption("Estimado con los precios del catálogo. El total real lo calcula el sistema al registrar.")

with flujo:
    # ─────────────────────────────── 2. Cliente ───────────────────────────────
    st.header("Cliente")
    cliente = st.session_state.cliente
    if cliente:
        with st.container(border=True, key="tarjeta_cliente"):
            datos, cambiar = st.columns([2, 1], vertical_alignment="center")
            datos.markdown(f":primary[:material/person:] **{cliente['nombre']}** · Documento {documento_cliente(cliente)}  \n"
                           f"{cliente['correo']} · {cliente['telefono']}")
            if cambiar.button("Cambiar cliente"):
                st.session_state.cliente = None
                st.rerun()
    else:
        buscar, nuevo = st.columns(2, gap="large")
        with buscar:
            texto = st.text_input("Buscar por documento o nombre", key="busqueda_cliente",
                                  placeholder="Ej.: 1020 o Laura")
            if texto.strip():
                q = texto.strip().lower()
                coincidencias = [c for c in leer("/clientes/") or []
                                 if q in c["documento"].lower() or q in c["nombre"].lower()]
                if coincidencias:
                    elegido = st.selectbox(f"Coincidencias ({len(coincidencias)})", coincidencias, key="cliente_elegido",
                                           format_func=lambda c: f"{c['nombre']} · {documento_cliente(c)}")
                    if st.button("Seleccionar cliente", type="primary", key="seleccionar_coincidencia"):
                        st.session_state.cliente = elegido
                        st.rerun()
                else:
                    st.info("No hay clientes con ese documento o nombre. Puedes registrarlo como cliente nuevo.")

            st.markdown("**Búsqueda exacta por tipo y número**")
            with st.form("busqueda_exacta", border=False):
                tipo_col, num_col = st.columns(2)
                tipo_b = tipo_col.selectbox("Tipo de documento", ["Todos", *TIPOS_DOCUMENTO], key="exacta_tipo")
                numero_b = num_col.text_input("Número", key="exacta_numero", placeholder="Ej.: 1020304050")
                st.caption("«Todos» también encuentra a los clientes sin clasificar.")
                if st.form_submit_button("Buscar", icon=":material/person_search:"):
                    st.session_state.exacta = buscar_exacto(numero_b.strip(), None if tipo_b == "Todos" else tipo_b)
            exacta = st.session_state.get("exacta", {})
            if "cliente" in exacta:
                c = exacta["cliente"]
                with st.container(border=True, key="tarjeta_exacta"):
                    st.markdown(f":primary[:material/person:] **{c['nombre']}** · Tipo de documento: "
                                f"**{tipo_doc(c['tipo'])}** · Número {c['documento']}  \n{c['correo']} · {c['telefono']}")
                    if st.button("Seleccionar cliente", type="primary", key="seleccionar_exacta"):
                        st.session_state.cliente = c
                        del st.session_state["exacta"]
                        st.rerun()
            elif "aviso" in exacta:
                st.warning(exacta["aviso"], icon=exacta["icono"])
            elif "error" in exacta:
                st.error(exacta["error"], icon=":material/error:")
        with nuevo, st.expander("Registrar cliente nuevo", icon=":material/person_add:"):
            with st.form("cliente_nuevo"):
                tipo_nuevo = st.selectbox("Tipo de documento", TIPOS_DOCUMENTO, index=None, format_func=NOMBRES_TIPO.get,
                                          placeholder="Elige el tipo")
                documento = st.text_input("Número de documento", help=REGLAS_DOCUMENTO)
                nombre = st.text_input("Nombre o razón social")
                correo = st.text_input("Correo")
                telefono = st.text_input("Teléfono")
                if st.form_submit_button("Registrar cliente", type="primary"):
                    if tipo_nuevo is None:
                        st.warning("Revisa los datos. Elige el tipo de documento.")
                    else:
                        try:
                            # El DTO del backend aplica la misma regla del documento según el tipo
                            nuevo_cliente = schemas.ClienteCreate(tipo=tipo_nuevo, documento=documento, nombre=nombre,
                                                                  correo=correo, telefono=telefono)
                        except ValidationError as e:
                            st.warning(aviso_validacion(e))
                        else:
                            try:
                                r = api_client.crear_cliente(nuevo_cliente.model_dump(mode="json"))
                            except requests.RequestException:
                                st.error("No hay conexión con la API: no se registró el cliente. Inténtalo de nuevo.")
                            else:
                                if r.status_code == 201:
                                    st.session_state.cliente = r.json()     # queda seleccionado
                                    leer.clear()
                                    st.rerun()
                                st.error(f"No se pudo registrar el cliente: {api_client.detalle_error(r)}")

    # ─────────────────────────────── 3. Pasajeros y registro ───────────────────────────────
    st.header("Pasajeros y registro")
    if "resultado" in st.session_state:
        panel_exito(st.session_state.resultado)

    if not st.session_state.reserva:
        st.info("Agrega al menos un producto a la reserva en curso.")
    elif not cliente:
        st.info("Selecciona o registra el cliente de la reserva.")
    else:
        st.markdown(f"Registrando como: **{asesor['nombre']}** · Cliente: **{cliente['nombre']}**")
        cantidad = st.number_input("Número de pasajeros", 1, 20, key="n_pasajeros")
        with st.form("confirmar"):
            for i in range(cantidad):
                # Columna angosta (el resumen va a la derecha): nombre en su fila; documento y fecha debajo
                st.text_input(f"Pasajero {i + 1}: nombre completo", key=f"pas_nombre_{i}")
                doc_col, nac_col = st.columns(2)
                doc_col.text_input("Documento", key=f"pas_documento_{i}")
                nac_col.date_input("Fecha de nacimiento", value=None, min_value=date(1920, 1, 1), max_value=HOY,
                                   format="DD/MM/YYYY", key=f"pas_nacimiento_{i}")
            enviar = st.form_submit_button("Registrar reserva", type="primary", icon=":material/check:")

        if enviar:
            estado = st.session_state
            try:
                nueva = schemas.ReservaCreate(
                    cliente_id=cliente["id"], asesor_id=asesor["id"],
                    items=[x["item"] for x in estado.reserva],
                    pasajeros=[{"nombre": estado[f"pas_nombre_{i}"], "documento": estado[f"pas_documento_{i}"],
                                "nacimiento": estado[f"pas_nacimiento_{i}"]} for i in range(cantidad)])
            except ValidationError as e:
                st.warning(aviso_validacion(e))
            else:
                try:
                    r = api_client.post("/reservas/", nueva.model_dump(mode="json"))
                except requests.RequestException:
                    st.error("No hay conexión con la API. La reserva en curso se conserva; inténtalo de nuevo.")
                else:
                    if r.status_code == 201:
                        # Lista: la reserva en curso, el cliente y los pasajeros se limpian para la siguiente
                        estado.resultado = r.json()
                        estado.reserva, estado.cliente = [], None
                        for clave in [k for k in estado if str(k).startswith(("pas_", "n_pasajeros", "busqueda_cliente",
                                                                               "exacta"))]:
                            del estado[clave]
                        leer.clear()
                        st.rerun()
                    st.error(f"No se pudo registrar la reserva: {api_client.detalle_error(r)} "
                             "La reserva en curso se conserva para que la ajustes.", icon=":material/error:")
