"""front/pages/02_Reservas.py — Consulta de reservas, registro de pagos y cancelaciones."""
import os
import sys
from datetime import date

import requests
import streamlit as st
from pydantic import ValidationError

import api_client
from estilo import INICIO, aplicar_estilo, encabezado_modulo, hora_bogota, pesos, requerir_asesor

# Mismos DTO del backend para pre-validar antes de tocar la red
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from back.app import schemas  # noqa: E402

st.set_page_config(page_title="Reservas · Brújula Viajes", page_icon="assets/logo_isotipo.png", layout="wide")
aplicar_estilo()
asesor = requerir_asesor()
encabezado_modulo("Reservas", "Consulta el detalle, registra pagos y gestiona cancelaciones.")

if not api_client.api_en_linea():
    st.warning("No hay conexión con la API. Levántala desde back/ con `uvicorn main:app --reload` "
               "y recarga la página.", icon=":material/cloud_off:")
    st.stop()

ESTADOS = ["Todas", "Pendiente", "Pagada", "Cancelada"]
COLOR_ESTADO = {"Pendiente": "orange", "Pagada": "primary", "Cancelada": "gray"}
MEDIOS = ["Efectivo", "Tarjeta", "Transferencia", "PSE"]
TIPOS = {"vuelo": "Vuelo", "hotel": "Hotel", "tour": "Tour", "paquete": "Paquete"}


def fecha_dia(iso: str) -> str:
    """Fechas de día (nacimiento, noches de hotel) llegan como 00:00 UTC: se muestra el día tal cual."""
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def fecha_item(item: dict, campo: str) -> str:
    return fecha_dia(item[campo]) if item["tipo"] == "hotel" else hora_bogota(item[campo])


def ver(codigo: str):
    st.session_state.res_codigo = codigo


def volver():
    st.session_state.pop("res_codigo", None)


def usuario_asesor() -> str | None:
    """Código del asesor en sesión, leído de la API en el momento de usarlo. Si ya no está activo,
    bloquea la operación con un aviso. El código no se guarda ni se muestra."""
    try:
        usuario = api_client.codigo_asesor_actual(asesor["id"])
    except requests.RequestException:
        st.error("No hay conexión con la API. Inténtalo de nuevo en un momento.")
        return None
    if not usuario:
        st.error("No pudimos confirmar tu usuario de asesor activo, así que la operación no se realizó. "
                 "Ingresa de nuevo desde el Inicio.", icon=":material/badge:")
        st.page_link(INICIO, label="Ir al Inicio", icon=":material/login:")
    return usuario


def tras_conflicto(res: dict, nombres: dict, mensaje: str):
    """409: otro asesor cambió la reserva primero. No se reintenta nada: se guarda el motivo y la página
    vuelve a leer la reserva (GET) para que el asesor decida con los datos frescos. La copia previa solo
    se usa si esa lectura falla."""
    st.session_state.res_conflicto = {"mensaje": mensaje, "res": res, "nombres": nombres}
    st.rerun()


def form_pago(res: dict, nombres: dict):
    codigo, saldo = res["codigo"], int(res["saldo"])
    with st.container(border=True, key="panel_pago"):
        st.markdown("#### :primary[:material/payments:] Registrar pago")
        with st.form("pago", clear_on_submit=True, border=False):
            valor = st.number_input("Valor del pago", min_value=1, max_value=saldo, value=None, step=1,
                                    help=f"Saldo: {pesos(saldo, markdown=True)}", placeholder=f"Hasta {pesos(saldo)}")
            st.caption(f"Saldo: {pesos(saldo, markdown=True)}")
            medio = st.selectbox("Medio de pago", MEDIOS)
            enviar = st.form_submit_button("Registrar pago", type="primary", icon=":material/check:")
        if not enviar:
            return
        if valor is None:
            # También llega vacío si el saldo bajó mientras se digitaba (otro pago) y el valor quedó por encima
            st.warning(f"Escribe un valor de pago entre {pesos(1, markdown=True)} y el saldo actual de "
                       f"{pesos(saldo, markdown=True)}.")
            return
        usuario = usuario_asesor()
        if not usuario:
            return
        try:
            pago = schemas.PagoCreate(valor=valor, medio=medio, usuario=usuario)
        except ValidationError as e:
            st.warning(f"Revisa los datos del pago: {e.errors()[0]['msg']}")
            return
        try:
            r = api_client.registrar_pago(codigo, pago.valor, pago.medio, pago.usuario)
        except requests.RequestException:
            st.error("No hay conexión con la API. El pago no se registró; inténtalo de nuevo.")
            return
        if r.status_code == 200:
            nueva = r.json()
            st.session_state.res_aviso = (f"Pago de {pesos(pago.valor, markdown=True)} registrado. "
                                          f"Nuevo saldo: {pesos(nueva['saldo'], markdown=True)} · "
                                          f"Estado: {nueva['estado']}.")
            st.rerun()
        if r.status_code == 409:
            tras_conflicto(res, nombres, f"No se pudo registrar el pago: {api_client.detalle_error(r)}")
        st.error(f"No se pudo registrar el pago: {api_client.detalle_error(r)}", icon=":material/error:")


def form_cancelar(res: dict, nombres: dict):
    codigo = res["codigo"]
    with st.container(border=True, key="panel_cancelar"):
        st.markdown("#### :primary[:material/event_busy:] Cancelar reserva")
        st.warning("La cancelación devuelve los cupos al inventario. Los pagos registrados se conservan "
                   "en la reserva.", icon=":material/info:")
        confirmar = st.checkbox("Confirmo que quiero cancelar esta reserva", key=f"confirmar_cancelacion_{codigo}")
        if not st.button("Cancelar reserva", icon=":material/close:", disabled=not confirmar,
                         key=f"cancelar_{codigo}"):
            return
        usuario = usuario_asesor()
        if not usuario:
            return
        try:
            datos = schemas.CancelarReserva(usuario=usuario)
            r = api_client.cancelar_reserva(codigo, datos.usuario)
        except requests.RequestException:
            st.error("No hay conexión con la API. La reserva no se canceló; inténtalo de nuevo.")
            return
        if r.status_code == 200:
            st.session_state.res_aviso = ("Reserva cancelada. Los cupos volvieron al inventario y los pagos "
                                          "registrados se conservan en la reserva.")
            st.session_state.pop(f"confirmar_cancelacion_{codigo}", None)
            st.rerun()
        if r.status_code == 409:
            tras_conflicto(res, nombres, f"No se pudo cancelar la reserva: {api_client.detalle_error(r)}")
        st.error(f"No se pudo cancelar la reserva: {api_client.detalle_error(r)}", icon=":material/error:")


def detalle(codigo: str):
    st.button("Volver a la lista", icon=":material/arrow_back:", on_click=volver)
    conflicto = st.session_state.pop("res_conflicto", None)     # 409 en la carga anterior
    try:
        r = api_client.obtener_reserva(codigo)
    except requests.RequestException:
        r = None
    desactualizada = False
    if r is not None and r.status_code == 200:
        res = r.json()
        nombres = api_client.mapa_asesores()    # una sola consulta por carga de página
    elif conflicto and (r is None or r.status_code != 404):
        # Falló la lectura de refresco tras el 409: se muestra lo que ya había en pantalla, con aviso
        res, nombres, desactualizada = conflicto["res"], conflicto["nombres"], True
    elif r is None:
        st.warning("No hay conexión con la API. Inténtalo de nuevo en un momento.")
        return
    elif r.status_code == 404:
        st.warning(f"No encontramos la reserva {codigo}. Revisa el código e inténtalo de nuevo.",
                   icon=":material/search_off:")
        return
    else:
        st.error(f"No se pudo consultar la reserva: {api_client.detalle_error(r)}")
        return

    if "res_aviso" in st.session_state:
        st.success(st.session_state.pop("res_aviso"), icon=":material/check_circle:")
    if conflicto:
        st.error(conflicto["mensaje"], icon=":material/error:")
        if desactualizada:
            st.warning("No pudimos volver a consultar la reserva, así que la información en pantalla puede "
                       "estar desactualizada.", icon=":material/sync_problem:")
        else:
            st.info("Actualizamos la reserva con los datos más recientes. Revisa el estado y el saldo antes "
                    "de continuar.", icon=":material/sync:")

    titulo, etiqueta = st.columns([4, 1], vertical_alignment="center")
    titulo.subheader(f"Reserva {res['codigo']}")
    with etiqueta, st.container(horizontal_alignment="right"):
        st.badge(res["estado"], color=COLOR_ESTADO.get(res["estado"], "gray"))
    st.caption(f"Creada el {hora_bogota(res['creada'])} (hora de Bogotá) · Registrada por {res['asesor']} · "
               f"Cliente: {res['cliente']['nombre']} ({res['cliente']['documento']})")

    total, pagado, saldo = st.columns(3)
    total.metric("Total", pesos(res["total"]), border=True)
    pagado.metric("Pagado", pesos(res["pagado"]), border=True)
    with saldo:
        if res["estado"] == "Cancelada":
            # Total menos pagado según la lectura actual: no es deuda por cobrar ni el valor al cancelarse
            st.metric("Importe restante (reserva cancelada)", pesos(res["saldo"]), border=True,
                      help="Total menos lo pagado, calculado con los datos actuales de la reserva.")
        else:
            with st.container(border=True, key="tarjeta_saldo"):
                st.metric("Saldo pendiente", pesos(res["saldo"]))

    st.markdown("#### Ítems")
    st.table([{"Producto": i["nombre"], "Tipo": TIPOS.get(i["tipo"], i["tipo"]), "Ciudad": i["ciudad"],
               "Inicio": fecha_item(i, "inicio"), "Fin": fecha_item(i, "fin"), "Cantidad": i["cantidad"],
               "Precio": pesos(i["precio"]), "Subtotal": pesos(i["subtotal"])} for i in res["items"]],
             hide_index=True)

    datos, linea = st.columns([3, 2], gap="large")
    with datos:
        st.markdown("#### Pasajeros")
        st.table([{"Nombre": p.get("nombre", ""), "Documento": p.get("documento", ""),
                       "Nacimiento": fecha_dia(p["nacimiento"]) if p.get("nacimiento") else ""}
                      for p in res["pasajeros"]], hide_index=True)
        st.markdown("#### Pagos")
        if res["pagos"]:
            st.table([{"Fecha": hora_bogota(p["fecha"]), "Valor": pesos(p["valor"]), "Medio": p["medio"]}
                          for p in res["pagos"]], hide_index=True)
        else:
            st.caption("Sin pagos registrados.")
    with linea:
        st.markdown("#### Historial")
        for h in res["historial"]:
            cambio = f"Reserva creada · {h['despues']}" if h["antes"] is None else f"{h['antes']} → {h['despues']}"
            # El historial guarda el código del asesor: en pantalla solo va su nombre
            quien = nombres.get(h["usuario"], "Asesor no identificado")
            st.markdown(f":primary[:material/radio_button_checked:] **{cambio}**  \n"
                        f"{hora_bogota(h['fecha'])} · {quien}")

    st.space("small")
    if res["estado"] == "Cancelada":
        conserva = " Los pagos registrados se conservan en la reserva." if res["pagos"] else ""
        st.info(f"Esta reserva está cancelada: ya no admite pagos ni cancelación.{conserva}",
                icon=":material/block:")
        return
    pago, cancelar = st.columns(2, gap="large")
    with pago:
        if res["saldo"] > 0:
            form_pago(res, nombres)
        else:
            st.info("La reserva no tiene saldo pendiente.", icon=":material/task_alt:")
    with cancelar:
        form_cancelar(res, nombres)


# ─────────────────────────────── Buscar ───────────────────────────────
por_codigo, filtros = st.columns([2, 3], gap="large")
with por_codigo, st.form("abrir_codigo", border=False):
    texto = st.text_input("Código de la reserva", placeholder="Ej.: RV-261106-D542")
    if st.form_submit_button("Abrir reserva", icon=":material/search:"):
        if texto.strip():
            ver(texto.strip().upper())
        else:
            st.warning("Escribe el código de la reserva.")
with filtros:
    estado_col, doc_col = st.columns(2)
    estado = estado_col.selectbox("Estado", ESTADOS, key="res_estado")
    documento = doc_col.text_input("Documento del cliente", key="res_documento", placeholder="Ej.: 1020304050")
st.divider()

if "res_codigo" in st.session_state:
    detalle(st.session_state.res_codigo)
    st.stop()

# ─────────────────────────────── Lista ───────────────────────────────
try:
    r = api_client.listar_reservas(estado=None if estado == "Todas" else estado,
                                   documento=documento.strip() or None)
except requests.RequestException:
    st.warning("No hay conexión con la API. Inténtalo de nuevo en un momento.")
    st.stop()
if r.status_code != 200:
    st.error(f"No se pudo consultar las reservas: {api_client.detalle_error(r)}")
    st.stop()
reservas = r.json()
if not reservas:
    st.info("Sin resultados para esos filtros.", icon=":material/search_off:")
else:
    st.caption(f"{len(reservas)} reserva(s), de la más reciente a la más antigua."
               + (" Se muestran las 50 más recientes; usa los filtros para acotar." if len(reservas) == 50 else ""))
for res in reservas:
    with st.container(border=True, key=f"panel_reserva_{res['codigo']}"):
        ident, est, total, pagado, saldo, accion = st.columns([2.6, 1.7, 1.2, 1.2, 1.2, 1.2],
                                                              vertical_alignment="center")
        ident.markdown(f"**{res['codigo']}**  \n{res['cliente']['nombre']} · {res['cliente']['documento']}")
        est.badge(res["estado"], color=COLOR_ESTADO.get(res["estado"], "gray"))
        est.caption(hora_bogota(res["creada"]))
        total.markdown(f":gray[Total]  \n**{pesos(res['total'], markdown=True)}**")
        pagado.markdown(f":gray[Pagado]  \n**{pesos(res['pagado'], markdown=True)}**")
        restante = "Importe restante (reserva cancelada)" if res["estado"] == "Cancelada" else "Saldo"
        saldo.markdown(f":gray[{restante}]  \n**{pesos(res['saldo'], markdown=True)}**")
        accion.button("Ver detalle", key=f"ver_{res['codigo']}", on_click=ver, args=(res["codigo"],))
