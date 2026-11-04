"""
datos_mongo.py — Datos de inicio de Brújula Viajes (mínimos del enunciado).

Los datos entran POR LA API (TestClient, sin levantar uvicorn), así pasan por las mismas
validaciones, copias de precio y descuentos de inventario que usará Streamlit.
Las fechas de producto son relativas a hoy (Bogotá), para que los datos no queden vencidos.
Ejecuta pruebas negativas (sobreventa, compensación, sobrepago, doble cancelación), reparte las
reservas en 3 meses con fechas de demostración y al final verifica los mínimos.

    cd back; python datos_mongo.py

⚠️ BORRA y vuelve a llenar la base brujula_viajes. No tiene vuelta atrás: todo dato que no venga
de este script se pierde. Si la configuración apunta a otra base, aborta sin crear, borrar ni
escribir nada.
"""
import sys
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import DB_NAME, client
from app.utils import BOGOTA, a_utc, ahora
from main import app

ESPERADA = "brujula_viajes"


def candado():
    """Atrapa una configuración equivocada: una variable MONGO_DB vieja en la terminal le gana al .env."""
    efectiva = client[DB_NAME].name
    print(f"Candado: DB_NAME = {DB_NAME}")
    print(f"Candado: client[DB_NAME].name = {efectiva}")
    if DB_NAME != ESPERADA or efectiva != ESPERADA:
        print(f"[x] Se encontró la base '{efectiva}' y se esperaba '{ESPERADA}'. "
              "No se creó, borró ni escribió nada.")
        sys.exit(1)


def llamar(api, metodo, url, datos=None, esperado=(200, 201), nota=""):
    r = api.request(metodo, url, json=datos)
    if r.status_code not in (esperado if isinstance(esperado, tuple) else (esperado,)):
        raise SystemExit(f"\n[x] {metodo} {url} -> {r.status_code}\n    {r.text}")
    if nota:
        detalle = r.json().get("detail", "") if r.status_code >= 400 else ""
        print(f"  [ok] {nota}: HTTP {r.status_code} {detalle}")
    return r.json()


def verificar(condicion, texto):
    assert condicion, texto
    print(f"  [ok] {texto}")


# ─────────────────────────────── Catálogo ───────────────────────────────
def cargar_catalogo(post, hoy):
    dia = lambda n: (hoy + timedelta(days=n)).isoformat()

    print("Catálogo")
    for iata, nombre in [("BOG", "Bogotá"), ("CTG", "Cartagena"), ("SMR", "Santa Marta"),
                         ("MDE", "Medellín"), ("ADZ", "San Andrés"), ("CLO", "Cali")]:
        post("/ciudades/", {"iata": iata, "nombre": nombre})

    def tarifas(basica, sillas_b=60):
        return [{"nombre": "Basica", "precio": basica, "equipaje": "Artículo personal", "sillas": sillas_b},
                {"nombre": "Clasica", "precio": basica + 70000, "equipaje": "Maleta de 23 kg", "sillas": 40},
                {"nombre": "Flexible", "precio": basica + 200000, "equipaje": "Maleta 23 kg + cambios", "sillas": 20}]

    # Horas en hora de Bogotá (-05:00); Mongo las guarda en UTC (punto 7)
    v = {}
    for codigo, aero, o, d, n, sale, llega, precio, sillas in [
        ("BV1234", "Avianca", "BOG", "CTG", 12, "07:00", "08:30", 250000, 60),
        ("BV1235", "Avianca", "CTG", "BOG", 16, "18:00", "19:30", 270000, 60),
        ("LA4021", "LATAM", "BOG", "SMR", 14, "06:00", "07:30", 230000, 60),
        ("LA4022", "LATAM", "SMR", "BOG", 17, "15:00", "16:30", 240000, 60),
        ("AV8101", "Avianca", "BOG", "MDE", 18, "08:00", "08:55", 180000, 60),
        ("AV8102", "Avianca", "MDE", "BOG", 21, "19:00", "19:55", 190000, 60),
        ("WG7310", "Wingo", "MDE", "ADZ", 25, "10:00", "12:00", 199000, 2),   # 2 sillas: prueba de sobreventa
        ("WG7311", "Wingo", "ADZ", "MDE", 29, "14:00", "16:00", 205000, 60),
        ("CM5501", "Clic", "CTG", "CLO", 32, "09:00", "10:40", 210000, 60),
        ("CM5502", "Clic", "CLO", "CTG", 36, "17:00", "18:40", 215000, 60),
        ("BV1240", "Avianca", "BOG", "CTG", 40, "07:00", "08:30", 260000, 60),
        ("BV1241", "Avianca", "CTG", "BOG", 45, "18:00", "19:30", 280000, 60),
    ]:
        v[codigo] = post("/vuelos/", {"codigo": codigo, "aerolinea": aero, "origen": o, "destino": d,
                                      "sale": f"{dia(n)}T{sale}:00-05:00", "llega": f"{dia(n)}T{llega}:00-05:00",
                                      "tarifas": tarifas(precio, sillas)})["id"]

    h = {}
    for clave, nombre, ciudad, dir_, est, coords, habs in [
        ("murallas", "Hotel Murallas", "CTG", "Cl. 34 #5-12", 4, [-75.548, 10.423],
         [("Doble", 2, 380000, 10), ("Familiar", 4, 620000, 4), ("Suite", 4, 900000, 2)]),
        ("bocagrande", "Casa Bocagrande", "CTG", "Cra. 2 #8-40", 3, [-75.556, 10.401],
         [("Sencilla", 1, 210000, 6), ("Doble", 2, 290000, 8)]),
        ("sierra", "Sierra Nevada Lodge", "SMR", "Km 7 vía Minca", 4, [-74.118, 11.143],
         [("Doble", 2, 340000, 6), ("Familiar", 4, 520000, 3)]),
        ("poblado", "Hotel Poblado Plaza", "MDE", "Cl. 10 #43-20", 4, [-75.568, 6.209],
         [("Sencilla", 1, 260000, 5), ("Doble", 2, 330000, 8)]),
        ("coral", "Posada Coral", "ADZ", "Av. Colombia #3-15", 3, [-81.700, 12.584],
         [("Doble", 2, 310000, 1)]),                         # 1 habitación: prueba de sobreventa
    ]:
        h[clave] = post("/hoteles/", {
            "nombre": nombre, "ciudad": ciudad, "direccion": dir_, "estrellas": est,
            "servicios": ["wifi", "desayuno"] + (["piscina"] if est >= 4 else []),
            "ubicacion": {"type": "Point", "coordinates": coords},
            "habitaciones": [{"tipo": t, "capacidad": c, "precio_noche": p, "cantidad": n}
                             for t, c, p, n in habs]})["id"]
        post(f"/hoteles/{h[clave]}/noches", {"desde": dia(0), "hasta": dia(60)})

    t, s = {}, {}
    for clave, nombre, ciudad, horas_, incluye, lugar, coords, hora, precio, cupos, dias in [
        ("islas", "Islas del Rosario", "CTG", 8, ["lancha", "almuerzo"], "Muelle La Bodeguita",
         [-75.547, 10.421], "08:00", 220000, 30, [13, 15, 41]),
        ("murallas", "Ciudad Amurallada a pie", "CTG", 3, ["guía bilingüe"], "Torre del Reloj",
         [-75.551, 10.423], "16:00", 90000, 20, [14, 34, 42]),
        ("tayrona", "Parque Tayrona", "SMR", 10, ["transporte", "entrada al parque"], "Parque de los Novios",
         [-74.212, 11.243], "06:00", 260000, 25, [15, 16, 30]),
        ("comuna13", "Comuna 13 Graffitour", "MDE", 4, ["guía local", "metrocable"], "Estación San Javier",
         [-75.613, 6.256], "09:00", 80000, 15, [19, 20, 27]),
        ("johnny", "Johnny Cay y Acuario", "ADZ", 6, ["lancha"], "Muelle Casa de la Cultura",
         [-81.695, 12.585], "09:00", 150000, 10, [26, 27]),
    ]:
        t[clave] = post("/tours/", {"nombre": nombre, "ciudad": ciudad, "horas": horas_, "incluye": incluye,
                                    "encuentro": {"lugar": lugar, "ubicacion": {"type": "Point", "coordinates": coords}}})["id"]
        for n in dias:
            s[(clave, n)] = post(f"/tours/{t[clave]}/salidas", {
                "tour_id": t[clave], "fecha": f"{dia(n)}T{hora}:00-05:00", "precio": precio, "cupos": cupos})["id"]

    # La venta abre antes del mes más antiguo de las reservas, para que su fecha de demostración
    # caiga dentro de la vigencia, y cierra antes del primer componente (la API lo exige).
    anio, mes = mes_relativo(hoy, 2)
    p = {}
    for clave, nombre, destino, descuento, ida, regreso, tarifa, n_ida, noches, hotel, tour, n_tour in [
        ("ctg", "Cartagena 4 noches", "CTG", 10, "BV1234", "BV1235", "Clasica", 12, 4, "murallas", "islas", 13),
        ("smr", "Santa Marta y Tayrona", "SMR", 8, "LA4021", "LA4022", "Basica", 14, 3, "sierra", "tayrona", 15),
        ("mde", "Medellín y Comuna 13", "MDE", 12, "AV8101", "AV8102", "Clasica", 18, 3, "poblado", "comuna13", 19),
    ]:
        creado = post("/paquetes/", {
            "nombre": nombre, "destino": destino, "descuento": descuento,
            "desde": date(anio, mes, 1).isoformat(), "hasta": dia(5),
            "componentes": [
                {"tipo": "vuelo", "ref_id": v[ida], "detalle": {"tarifa": tarifa}},
                {"tipo": "vuelo", "ref_id": v[regreso], "detalle": {"tarifa": tarifa}},
                {"tipo": "hotel", "ref_id": h[hotel],
                 "detalle": {"tipo_hab": "Doble", "noches": noches, "entrada": dia(n_ida)}},
                {"tipo": "tour", "ref_id": t[tour], "detalle": {"salida_id": s[(tour, n_tour)]}}]})
        # Fórmula de cotizar_paquete sobre las COPIAS que devolvió la API, sin números quemados
        precio = round(sum(c["precio"] for c in creado["componentes"]) * (1 - creado["descuento"] / 100))
        p[clave] = {"id": creado["id"], "precio": precio}
        print(f"  {nombre}: -{descuento}% = {precio:,} por persona")
    return v, h, t, s, p


def cargar_personas(post):
    print("Clientes y asesores")
    c = {}
    for doc, nombre, correo, tel, nacimiento, pref in [
        ("1020304050", "Laura Gomez", "laura@mail.com", "3001234567", "1998-04-12",
         {"favoritos": ["CTG", "SMR"], "presupuesto": 3500000, "con_ninos": False}),
        ("79856412", "Andres Rojas", "andres.rojas@mail.com", "3157894561", "1985-02-20", None),
        ("1032456789", "Camila Torres", "camila.t@mail.com", "3204567812", "1990-05-30",
         {"favoritos": ["CTG"], "presupuesto": 6000000, "con_ninos": True}),
        ("52114789", "Marcela Vargas", "marcela.v@mail.com", "3112223344", "1979-11-02",
         {"favoritos": ["MDE"], "presupuesto": 8000000, "con_ninos": True}),
        ("80123456", "Felipe Castro", "fcastro@mail.com", "3123334455", "1982-08-17", None),
        ("1015998877", "Valentina Rios", "vale.rios@mail.com", "3134445566", "1996-01-25",
         {"favoritos": ["SMR", "ADZ"], "presupuesto": 2500000, "con_ninos": False}),
        ("1098765432", "Santiago Mejia", "smejia@mail.com", "3145556677", "1994-06-09", None),
        ("43567123", "Gloria Ospina", "gloria.ospina@mail.com", "3006667788", "1971-03-14",
         {"favoritos": ["CTG", "CLO"], "presupuesto": 5000000, "con_ninos": False}),
        ("1144056789", "Daniel Mosquera", "dmosquera@mail.com", "3167778899", "1992-10-30", None),
        ("66998877", "Patricia Lozano", "plozano@mail.com", "3178889900", "1975-12-05",
         {"favoritos": ["ADZ"], "presupuesto": 4000000, "con_ninos": True}),
        ("1023456001", "Juan Pablo Niño", "jpnino@mail.com", "3189990011", "2000-07-21", None),
        ("1007654321", "Isabella Herrera", "isa.herrera@mail.com", "3190001122", "2001-02-11",
         {"favoritos": ["SMR"], "presupuesto": 1800000, "con_ninos": False}),
        ("71234567", "Ricardo Salazar", "rsalazar@mail.com", "3101112233", "1968-09-28", None),
        ("1053778899", "Natalia Cardenas", "ncardenas@mail.com", "3209998877", "1989-04-03",
         {"favoritos": ["MDE", "CTG"], "presupuesto": 7000000, "con_ninos": True}),
        ("1088223344", "Sebastian Ortiz", "sortiz@mail.com", "3218887766", "1997-05-16", None),
        ("39445566", "Claudia Beltran", "cbeltran@mail.com", "3227776655", "1980-01-19",
         {"favoritos": ["CLO"], "presupuesto": 3000000, "con_ninos": False}),
    ]:
        datos = {"documento": doc, "nombre": nombre, "correo": correo, "telefono": tel}
        if pref:
            datos["preferencias"] = pref
        c[doc] = {"id": post("/clientes/", datos)["id"], "pasajero": (nombre, doc, nacimiento)}
    a = {}
    for cod, nombre, correo, activo in [("AS-01", "Carlos Perez", "cperez@brujula.co", True),
                                        ("AS-02", "Diana Ruiz", "druiz@brujula.co", True),
                                        ("AS-03", "Jorge Mejia", "jmejia@brujula.co", False)]:
        a[cod] = post("/asesores/", {"codigo": cod, "nombre": nombre, "correo": correo, "activo": activo})["id"]
    return c, a


# ─────────────────────────────── Reservas ───────────────────────────────
ACOMPANANTES = [("Sofia Mora", "1020304051", "2000-09-03"), ("Paula Diaz", "52789456", "1987-07-11"),
                ("Mateo Leon", "1143567890", "2016-03-14"), ("Lucia Prieto", "1143567891", "2018-08-22"),
                ("Tomas Arias", "1011223344", "1995-12-01"), ("Elena Duarte", "41556677", "1964-06-27"),
                ("Martin Vega", "1011223345", "2012-02-09")]


def cargar_reservas(post, cat, c, a, dia):
    v, h, t, s, p = cat
    vuelos = lambda ida, regreso, tarifa, n: [{"tipo": "vuelo", "ref_id": v[x], "tarifa": tarifa, "cantidad": n}
                                              for x in (ida, regreso)]
    hotel = lambda clave, tipo, entrada, noches, n: [{
        "tipo": "hotel", "ref_id": h[clave], "tipo_hab": tipo, "cantidad": n,
        "entrada": dia(entrada), "salida": dia(entrada + noches)}]
    tour = lambda clave, n_dia, n: [{"tipo": "tour", "ref_id": t[clave], "salida_id": s[(clave, n_dia)], "cantidad": n}]
    paquete = lambda clave, n: [{"tipo": "paquete", "ref_id": p[clave]["id"], "cantidad": n}]
    precios = {x["id"]: x["precio"] for x in p.values()}

    # n.º | meses atrás | día del mes (None en el mes actual) | cliente | asesor | ítems | pagos | ¿cancelar?
    # Un pago (medio, None) cubre todo el saldo y deja la reserva Pagada.
    filas = [
        (1, 2, 4, "1020304050", "AS-01", vuelos("BV1234", "BV1235", "Basica", 2),
         [("PSE", .5), ("Tarjeta", None)], False),
        (2, 2, 6, "79856412", "AS-02", paquete("ctg", 2), [("Tarjeta", .5), ("Transferencia", None)], False),
        (3, 2, 9, "1032456789", "AS-01", hotel("murallas", "Familiar", 12, 3, 4) + tour("murallas", 14, 4),
         [], True),                                                     # devuelve noches: prueba negativa
        (4, 2, 11, "1015998877", "AS-02", paquete("smr", 1), [("Efectivo", None)], False),
        (5, 2, 14, "1098765432", "AS-01", hotel("poblado", "Sencilla", 18, 2, 1), [("PSE", None)], False),
        (6, 2, 18, "43567123", "AS-02", tour("tayrona", 16, 3), [("Transferencia", None)], False),
        (7, 2, 22, "80123456", "AS-01", vuelos("AV8101", "AV8102", "Clasica", 1), [("PSE", .3)], False),
        (8, 2, 26, "66998877", "AS-02", hotel("sierra", "Familiar", 28, 3, 4) + tour("tayrona", 30, 4),
         [("Tarjeta", .25), ("Efectivo", .25), ("PSE", None)], False),

        (9, 1, 3, "52114789", "AS-02", paquete("mde", 4), [("Transferencia", .5), ("Tarjeta", None)], False),
        (10, 1, 7, "1144056789", "AS-01", vuelos("CM5501", "CM5502", "Flexible", 2), [("Tarjeta", None)], False),
        (11, 1, 10, "1053778899", "AS-02", hotel("bocagrande", "Doble", 40, 4, 2) + vuelos("BV1240", "BV1241", "Basica", 2),
         [("Efectivo", .2)], False),
        (12, 1, 13, "1023456001", "AS-01", paquete("ctg", 1), [("PSE", .3)], True),   # cancelada con abono
        (13, 1, 17, "1007654321", "AS-02", vuelos("WG7310", "WG7311", "Clasica", 2) + tour("johnny", 26, 2),
         [("Tarjeta", .5), ("PSE", None)], False),
        (14, 1, 21, "1088223344", "AS-01", paquete("smr", 2), [], False),
        (15, 1, 25, "71234567", "AS-02", hotel("murallas", "Suite", 33, 2, 2), [("Efectivo", None)], False),

        (16, 0, None, "39445566", "AS-01", paquete("mde", 2), [("Tarjeta", None)], False),
        (17, 0, None, "79856412", "AS-01", hotel("coral", "Doble", 25, 3, 2), [], False),   # agota la única Doble
        (18, 0, None, "1098765432", "AS-02", vuelos("BV1240", "BV1241", "Clasica", 1),
         [("Tarjeta", None)], True),                                    # Pagada y luego cancelada
        (19, 0, None, "1032456789", "AS-02", paquete("ctg", 4),
         [("PSE", .25), ("Transferencia", .25), ("Tarjeta", None)], False),
        (20, 0, None, "80123456", "AS-01", tour("comuna13", 20, 2), [("Efectivo", .5)], False),
        (21, 0, None, "1020304050", "AS-02", hotel("bocagrande", "Sencilla", 33, 2, 1), [], True),
        (22, 0, None, "43567123", "AS-01", tour("islas", 41, 4), [], False),
    ]

    print("Reservas")
    creadas = {}
    for i, (num, atras, dia_mes, doc, asesor, items, pagos, cancelar) in enumerate(filas):
        cantidad = max(it["cantidad"] for it in items)
        pasajeros = [c[doc]["pasajero"]] + [ACOMPANANTES[(i + k) % len(ACOMPANANTES)] for k in range(cantidad - 1)]
        r = post("/reservas/", {"cliente_id": c[doc]["id"], "asesor_id": a[asesor], "items": items,
                                "pasajeros": [{"nombre": n, "documento": d, "nacimiento": f} for n, d, f in pasajeros]})
        for it in r["items"]:
            if it["tipo"] == "paquete":
                assert it["precio"] == precios[it["ref_id"]], (it["precio"], precios[it["ref_id"]])
        for medio, fraccion in pagos:
            valor = r["saldo"] if fraccion is None else round(r["total"] * fraccion / 1000) * 1000
            r = post(f"/reservas/{r['codigo']}/pagos", {"valor": valor, "medio": medio, "usuario": asesor})
        if cancelar:
            r = post(f"/reservas/{r['codigo']}/cancelar", {"usuario": asesor})
        creadas[num] = {"codigo": r["codigo"], "atras": atras, "dia": dia_mes, "saldo": r["saldo"]}
        tipos = "+".join(sorted({it["tipo"] for it in r["items"]}))
        print(f"  {num:>2}. {r['codigo']}  {tipos:<12} ×{cantidad}  {r['total']:>10,}  pagado {r['pagado']:>10,}  {r['estado']}")
    return creadas


def pruebas_negativas(post, get, cat, c, a, creadas, dia):
    v, h, _, _, _ = cat
    print("Pruebas negativas (deben fallar)")
    laura = c["1020304050"]
    pax = [{"nombre": n, "documento": d, "nacimiento": f}
           for n, d, f in (laura["pasajero"], ACOMPANANTES[0])]
    canc, coral, pend = creadas[3]["codigo"], creadas[17]["codigo"], creadas[7]

    noches = get(f"/hoteles/{h['murallas']}/noches?tipo=Familiar&desde={dia(12)}&hasta={dia(15)}")
    assert len(noches) == 3 and all(n["libres"] == 4 for n in noches), "la cancelación no devolvió las noches"
    print(f"  [ok] Cancelación de {canc} devolvió las 3 noches Familiar (libres = 4)")

    post("/reservas/", {"cliente_id": laura["id"], "asesor_id": a["AS-01"], "pasajeros": pax[:1],
                        "items": [{"tipo": "hotel", "ref_id": h["coral"], "tipo_hab": "Doble",
                                   "entrada": dia(26), "salida": dia(27), "cantidad": 1}]},
         esperado=409, nota=f"Sobreventa de hotel (Doble agotada por {coral})")

    antes = get(f"/vuelos/{v['WG7310']}")["tarifas"][0]["libres"]
    post("/reservas/", {"cliente_id": laura["id"], "asesor_id": a["AS-01"], "pasajeros": pax,
                        "items": [{"tipo": "vuelo", "ref_id": v["WG7310"], "tarifa": "Basica", "cantidad": 2},
                                  {"tipo": "hotel", "ref_id": h["coral"], "tipo_hab": "Doble",
                                   "entrada": dia(25), "salida": dia(28), "cantidad": 2}]},
         esperado=409, nota="Vuelo OK + hotel lleno")
    despues = get(f"/vuelos/{v['WG7310']}")["tarifas"][0]["libres"]
    assert antes == despues == 2, (antes, despues)
    print(f"  [ok] Compensación: las sillas del WG7310 siguen en {despues} (se descontaron y se devolvieron)")

    post("/reservas/", {"cliente_id": laura["id"], "asesor_id": a["AS-01"], "pasajeros": pax[:1],
                        "items": [{"tipo": "vuelo", "ref_id": v["WG7310"], "tarifa": "Basica", "cantidad": 3}]},
         esperado=409, nota="Sobreventa de vuelo")
    post(f"/reservas/{pend['codigo']}/pagos", {"valor": pend["saldo"] + 1, "medio": "PSE", "usuario": "AS-01"},
         esperado=400, nota="Sobrepago")
    post(f"/reservas/{canc}/pagos", {"valor": 1000, "medio": "PSE", "usuario": "AS-01"},
         esperado=400, nota="Pago a reserva cancelada")
    post(f"/reservas/{canc}/cancelar", {"usuario": "AS-01"}, esperado=400, nota="Doble cancelación")
    post(f"/reservas/{pend['codigo']}/pagos", {"valor": 1000, "medio": "PSE", "usuario": "AS-03"},
         esperado=400, nota="Asesor inactivo")
    post("/vuelos/", {"codigo": "XX1", "aerolinea": "X", "origen": "BOG", "destino": "CTG",
                      "sale": f"{dia(20)}T10:00:00-05:00", "llega": f"{dia(20)}T11:00:00-05:00",
                      "tarifas": [{"nombre": "Basica", "precio": 1, "equipaje": "x", "sillas": 1, "libres": 999}]},
         esperado=422, nota="Cliente intenta fijar 'libres'")


# ─────────────────── Fechas de demostración: en producción las pone la API ───────────────────
def mes_relativo(hoy, atras):
    """(año, mes) de Bogotá, `atras` meses antes del mes de hoy."""
    anio, mes0 = divmod(hoy.year * 12 + hoy.month - 1 - atras, 12)
    return anio, mes0 + 1


def instante_creada(hoy, ahora_, atras, dia_mes, k, n):
    """Meses pasados: día fijo, lejos del borde (B1 agrupa por mes de Bogotá). Mes actual: k-ésimo
    de n instantes repartidos entre el inicio del mes y ahora, porque aún no hay días posteriores."""
    anio, mes = mes_relativo(hoy, atras)
    if atras:
        return datetime(anio, mes, dia_mes, 9 + k % 8, (7 * k) % 60, tzinfo=BOGOTA)
    inicio = datetime(anio, mes, 1, tzinfo=BOGOTA)
    t = inicio + (ahora_ - inicio) * (k + 1) / (n + 1)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


def momentos_posteriores(creada, n, ahora_):
    """n instantes en orden después de creada: cada 2 días si cabe; si no, repartidos hasta ahora."""
    paso = timedelta(days=2, hours=3)
    if creada + paso * n > ahora_:
        paso = (ahora_ - creada) / (n + 1)
    instantes = [creada + paso * (i + 1) for i in range(n)]
    return [t.replace(microsecond=t.microsecond // 1000 * 1000) for t in instantes]


def fechar_reservas(db, creadas, hoy):
    """Reparte las reservas en 3 meses, algo que la API no permite porque siempre usa la hora actual.
    Solo cambian creada, pagos[].fecha e historial[].fecha. NO se cambia el codigo: su prefijo conserva
    la fecha real de generación. El inventario tampoco: la API ya lo descontó y lo devolvió."""
    ahora_ = ahora()
    grupos = {}
    for fila in creadas.values():
        grupos.setdefault(fila["atras"], []).append(fila)
    for atras, filas in grupos.items():
        for k, fila in enumerate(filas):
            r = db.reservas.find_one({"codigo": fila["codigo"]})
            creada = instante_creada(hoy, ahora_, atras, fila["dia"], k, len(filas))
            cancelada = r["estado"] == "Cancelada"
            momentos = momentos_posteriores(creada, len(r["pagos"]) + cancelada, ahora_)
            pagos = [{**pago, "fecha": momentos[i]} for i, pago in enumerate(r["pagos"])]
            historial = []
            for evento in r["historial"]:
                if evento["despues"] == "Pendiente":
                    fecha = creada
                elif evento["despues"] == "Pagada":
                    fecha = pagos[-1]["fecha"]                # el último pago la marcó Pagada
                else:
                    fecha = momentos[-1]                      # la cancelación va después de los pagos
                historial.append({**evento, "fecha": fecha})
            db.reservas.update_one({"_id": r["_id"]},
                                   {"$set": {"creada": creada, "pagos": pagos, "historial": historial}})


# ─────────────────────────────── Verificación ───────────────────────────────
def verificar_minimos(db, get, hoy):
    print("Mínimos del enunciado")
    conteo = lambda col: db[col].count_documents({})
    verificar(conteo("ciudades") >= 4, f"ciudades >= 4 ({conteo('ciudades')})")

    rutas = {(x["origen"], x["destino"]) for x in db.vuelos.find({}, {"origen": 1, "destino": 1})}
    verificar(conteo("vuelos") >= 10, f"vuelos >= 10 ({conteo('vuelos')})")
    verificar(all((d, o) in rutas for o, d in rutas), f"cada ruta tiene regreso ({len(rutas)} rutas)")

    ciudades = db.hoteles.distinct("ciudad")
    verificar(conteo("hoteles") >= 5 and len(ciudades) >= 3,
              f"hoteles >= 5 en >= 3 ciudades ({conteo('hoteles')} en {len(ciudades)})")
    verificar(conteo("tours") >= 5, f"tours >= 5 ({conteo('tours')})")
    salidas = list(db.salidas.aggregate([{"$group": {"_id": "$tour_id", "n": {"$sum": 1}}}]))
    verificar(len(salidas) == conteo("tours") and all(x["n"] >= 2 for x in salidas),
              f"cada tour con varias salidas (mínimo {min(x['n'] for x in salidas)})")

    vigentes = get("/paquetes/")
    verificar(len(vigentes) >= 3, f"paquetes vigentes hoy >= 3 ({len(vigentes)})")
    verificar(conteo("clientes") >= 15, f"clientes >= 15 ({conteo('clientes')})")
    verificar(conteo("asesores") >= 3, f"asesores >= 3 ({conteo('asesores')})")

    estados = {x["_id"]: x["n"] for x in db.reservas.aggregate(
        [{"$group": {"_id": "$estado", "n": {"$sum": 1}}}])}
    verificar(conteo("reservas") >= 20, f"reservas >= 20 ({conteo('reservas')})")
    verificar(set(estados) == {"Pendiente", "Pagada", "Cancelada"}, f"los 3 estados presentes ({estados})")

    meses = {x["_id"]: x["n"] for x in db.reservas.aggregate([{"$group": {
        "_id": {"$dateToString": {"date": "$creada", "format": "%Y-%m", "timezone": "America/Bogota"}},
        "n": {"$sum": 1}}}])}
    esperados = {"{}-{:02d}".format(*mes_relativo(hoy, a)): n for a, n in [(2, 8), (1, 7), (0, 7)]}
    verificar(len(meses) >= 3 and meses == esperados, f"creadas en >= 3 meses de Bogotá ({dict(sorted(meses.items()))})")

    # Próximos 30 días del enunciado: una noche por día para cada hotel y tipo, sin huecos
    dias = {a_utc(hoy + timedelta(days=i)) for i in range(30)}
    tipos = 0
    for hotel in db.hoteles.find():
        for hab in hotel["habitaciones"]:
            fechas = {n["fecha"] for n in db.noches.find({"hotel_id": hotel["_id"], "tipo": hab["tipo"],
                                                          "fecha": {"$gte": min(dias), "$lte": max(dias)}})}
            assert fechas == dias, (hotel["nombre"], hab["tipo"], sorted(dias - fechas))
            tipos += 1
    print(f"  [ok] noches sin huecos en [hoy, hoy+30) para {tipos} combinaciones de hotel y tipo")


def main():
    candado()                                          # antes de drop_database y de TestClient
    hoy = datetime.now(BOGOTA).date()
    dia = lambda n: (hoy + timedelta(days=n)).isoformat()
    print(f"Hoy en Bogotá: {hoy}")
    client.drop_database(DB_NAME)
    with TestClient(app) as api:                       # dispara init_db() (validadores + índices)
        post = lambda url, d, **k: llamar(api, "POST", url, d, **k)
        get = lambda url, **k: llamar(api, "GET", url, **k)

        cat = cargar_catalogo(post, hoy)
        c, a = cargar_personas(post)
        creadas = cargar_reservas(post, cat, c, a, dia)
        pruebas_negativas(post, get, cat, c, a, creadas, dia)

        db = client[DB_NAME]
        fechar_reservas(db, creadas, hoy)
        verificar_minimos(db, get, hoy)

        print("\nResumen")
        for col in ["ciudades", "vuelos", "hoteles", "noches", "tours", "salidas",
                    "paquetes", "clientes", "asesores", "reservas"]:
            print(f"  {col:<9} {db[col].count_documents({}):>5}")
        print(f"\nListo. Base: {DB_NAME}. Levanta la API con:  cd back; uvicorn main:app --reload  ->  http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
