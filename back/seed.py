"""
seed.py — Datos de prueba de Brújula Viajes.

Los datos entran POR LA API (TestClient, sin levantar uvicorn), así pasan por las mismas
validaciones, copias de precio y descuentos de inventario que usará Streamlit.
Al final ejecuta pruebas negativas: sobreventa, compensación, sobrepago y doble cancelación.

    cd back && python seed.py    # ⚠️ BORRA la base brujula_viajes y la vuelve a llenar
"""
from fastapi.testclient import TestClient

from app.database import DB_NAME, client
from main import app


def llamar(api, metodo, url, datos=None, esperado=(200, 201), nota=""):
    r = api.request(metodo, url, json=datos)
    if r.status_code not in (esperado if isinstance(esperado, tuple) else (esperado,)):
        raise SystemExit(f"\n[x] {metodo} {url} -> {r.status_code}\n    {r.text}")
    if nota:
        detalle = r.json().get("detail", "") if r.status_code >= 400 else ""
        print(f"  [ok] {nota}: HTTP {r.status_code} {detalle}")
    return r.json()


def main():
    client.drop_database(DB_NAME)
    with TestClient(app) as api:                       # dispara init_db() (validadores + índices)
        post = lambda url, d, **k: llamar(api, "POST", url, d, **k)
        get = lambda url, **k: llamar(api, "GET", url, **k)

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
        for codigo, aero, o, d, sale, llega, precio, sillas in [
            ("BV1234", "Avianca", "BOG", "CTG", "2026-12-18T07:00", "2026-12-18T08:30", 250000, 60),
            ("BV1235", "Avianca", "CTG", "BOG", "2026-12-22T18:00", "2026-12-22T19:30", 270000, 60),
            ("LA4021", "LATAM", "BOG", "SMR", "2026-12-20T06:00", "2026-12-20T07:30", 230000, 60),
            ("LA4022", "LATAM", "SMR", "BOG", "2026-12-27T15:00", "2026-12-27T16:30", 240000, 60),
            ("WG7310", "Wingo", "MDE", "ADZ", "2027-01-08T10:00", "2027-01-08T12:00", 199000, 2),
        ]:
            v[codigo] = post("/vuelos/", {"codigo": codigo, "aerolinea": aero, "origen": o, "destino": d,
                                          "sale": sale + ":00-05:00", "llega": llega + ":00-05:00",
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
            post(f"/hoteles/{h[clave]}/noches", {"desde": "2026-12-01", "hasta": "2027-02-01"})

        t, s = {}, {}
        for clave, nombre, ciudad, horas, incluye, lugar, coords, salidas in [
            ("islas", "Islas del Rosario", "CTG", 8, ["lancha", "almuerzo"], "Muelle La Bodeguita",
             [-75.547, 10.421], [("2026-12-19T08:00", 220000, 30), ("2026-12-21T08:00", 220000, 30)]),
            ("murallas", "Ciudad Amurallada a pie", "CTG", 3, ["guía bilingüe"], "Torre del Reloj",
             [-75.551, 10.423], [("2026-12-28T16:00", 90000, 20)]),
            ("tayrona", "Parque Tayrona", "SMR", 10, ["transporte", "entrada al parque"], "Parque de los Novios",
             [-74.212, 11.243], [("2026-12-21T06:00", 260000, 25)]),
            ("comuna13", "Comuna 13 Graffitour", "MDE", 4, ["guía local", "metrocable"], "Estación San Javier",
             [-75.613, 6.256], [("2027-01-09T09:00", 80000, 15)]),
            ("johnny", "Johnny Cay y Acuario", "ADZ", 6, ["lancha"], "Muelle Casa de la Cultura",
             [-81.695, 12.585], [("2027-01-09T09:00", 150000, 10)]),
        ]:
            t[clave] = post("/tours/", {"nombre": nombre, "ciudad": ciudad, "horas": horas, "incluye": incluye,
                                        "encuentro": {"lugar": lugar, "ubicacion": {"type": "Point", "coordinates": coords}}})["id"]
            for fecha, precio, cupos in salidas:
                s[(clave, fecha[:10])] = post(f"/tours/{t[clave]}/salidas", {
                    "tour_id": t[clave], "fecha": fecha + ":00-05:00", "precio": precio, "cupos": cupos})["id"]

        p_ctg = post("/paquetes/", {
            "nombre": "Cartagena 4 noches", "destino": "CTG", "descuento": 10,
            "desde": "2026-11-01", "hasta": "2026-12-17",
            "componentes": [
                {"tipo": "vuelo", "ref_id": v["BV1234"], "detalle": {"tarifa": "Clasica"}},
                {"tipo": "hotel", "ref_id": h["murallas"], "detalle": {"tipo_hab": "Doble", "noches": 4, "entrada": "2026-12-18"}},
                {"tipo": "tour", "ref_id": t["islas"], "detalle": {"salida_id": s[("islas", "2026-12-19")]}}]})["id"]
        p_smr = post("/paquetes/", {
            "nombre": "Santa Marta y Tayrona", "destino": "SMR", "descuento": 8,
            "desde": "2026-11-01", "hasta": "2026-12-19",
            "componentes": [
                {"tipo": "vuelo", "ref_id": v["LA4021"], "detalle": {"tarifa": "Basica"}},
                {"tipo": "hotel", "ref_id": h["sierra"], "detalle": {"tipo_hab": "Doble", "noches": 3, "entrada": "2026-12-20"}},
                {"tipo": "tour", "ref_id": t["tayrona"], "detalle": {"salida_id": s[("tayrona", "2026-12-21")]}}]})["id"]

        print("Clientes y asesores")
        c = {}
        for doc, nombre, correo, tel, pref in [
            ("1020304050", "Laura Gomez", "laura@mail.com", "3001234567",
             {"favoritos": ["CTG", "SMR"], "presupuesto": 3500000, "con_ninos": False}),
            ("79856412", "Andres Rojas", "andres.rojas@mail.com", "3157894561", None),
            ("1032456789", "Camila Torres", "camila.t@mail.com", "3204567812",
             {"favoritos": ["CTG"], "presupuesto": 6000000, "con_ninos": True}),
        ]:
            datos = {"documento": doc, "nombre": nombre, "correo": correo, "telefono": tel}
            if pref:
                datos["preferencias"] = pref
            c[doc] = post("/clientes/", datos)["id"]
        a = {}
        for cod, nombre, correo, activo in [("AS-01", "Carlos Perez", "cperez@brujula.co", True),
                                            ("AS-02", "Diana Ruiz", "druiz@brujula.co", True),
                                            ("AS-03", "Jorge Mejia", "jmejia@brujula.co", False)]:
            a[cod] = post("/asesores/", {"codigo": cod, "nombre": nombre, "correo": correo, "activo": activo})["id"]

        pax = lambda *ps: [{"nombre": n, "documento": d, "nacimiento": f} for n, d, f in ps]
        laura = ("Laura Gomez", "1020304050", "1998-04-12")
        sofia = ("Sofia Gomez", "1020304051", "2000-09-03")

        print("Reservas")
        r1 = post("/reservas/", {"cliente_id": c["1020304050"], "asesor_id": a["AS-01"], "pasajeros": pax(laura, sofia),
                                 "items": [{"tipo": "vuelo", "ref_id": v["BV1234"], "tarifa": "Basica", "cantidad": 2},
                                           {"tipo": "vuelo", "ref_id": v["BV1235"], "tarifa": "Basica", "cantidad": 2}]})
        post(f"/reservas/{r1['codigo']}/pagos", {"valor": 200000, "medio": "PSE", "usuario": "AS-01"})
        print(f"  {r1['codigo']}  vuelos ida y vuelta, abono parcial -> Pendiente")

        r2 = post("/reservas/", {"cliente_id": c["79856412"], "asesor_id": a["AS-02"],
                                 "pasajeros": pax(("Andres Rojas", "79856412", "1985-02-20"),
                                                  ("Paula Diaz", "52789456", "1987-07-11")),
                                 "items": [{"tipo": "paquete", "ref_id": p_ctg, "cantidad": 2}]})
        assert r2["total"] == 2 * 1854000, r2["total"]              # (320k + 1.52M + 220k) × 0,9 × 2
        post(f"/reservas/{r2['codigo']}/pagos", {"valor": 1708000, "medio": "Tarjeta", "usuario": "AS-02"})
        r2 = post(f"/reservas/{r2['codigo']}/pagos", {"valor": 2000000, "medio": "Transferencia", "usuario": "AS-02"})
        assert r2["estado"] == "Pagada"
        print(f"  {r2['codigo']}  paquete Cartagena ×2 = {r2['total']:,} pagado en dos cuotas -> Pagada")

        r3 = post("/reservas/", {"cliente_id": c["1032456789"], "asesor_id": a["AS-01"],
                                 "pasajeros": pax(("Camila Torres", "1032456789", "1990-05-30"),
                                                  ("Mateo Torres", "1143567890", "2016-03-14")),
                                 "items": [{"tipo": "hotel", "ref_id": h["murallas"], "tipo_hab": "Familiar",
                                            "entrada": "2026-12-27", "salida": "2026-12-30", "cantidad": 4},
                                           {"tipo": "tour", "ref_id": t["murallas"],
                                            "salida_id": s[("murallas", "2026-12-28")], "cantidad": 4}]})
        post(f"/reservas/{r3['codigo']}/cancelar", {"usuario": "AS-01"})
        print(f"  {r3['codigo']}  hotel + tour, cancelada -> inventario devuelto")

        r4 = post("/reservas/", {"cliente_id": c["1020304050"], "asesor_id": a["AS-02"], "pasajeros": pax(laura),
                                 "items": [{"tipo": "paquete", "ref_id": p_smr, "cantidad": 1}]})
        print(f"  {r4['codigo']}  paquete Santa Marta ×1 sin pagos -> Pendiente")

        r5 = post("/reservas/", {"cliente_id": c["79856412"], "asesor_id": a["AS-01"],
                                 "pasajeros": pax(("Andres Rojas", "79856412", "1985-02-20")),
                                 "items": [{"tipo": "hotel", "ref_id": h["coral"], "tipo_hab": "Doble",
                                            "entrada": "2027-01-08", "salida": "2027-01-11", "cantidad": 2}]})
        print(f"  {r5['codigo']}  agota la única Doble de Posada Coral (8–11 ene)")

        print("Pruebas negativas (deben fallar)")
        noches = get(f"/hoteles/{h['murallas']}/noches?tipo=Familiar&desde=2026-12-27&hasta=2026-12-30")
        assert all(n["libres"] == 4 for n in noches), "la cancelación no devolvió las noches"
        print("  [ok] Cancelación devolvió las 3 noches Familiar (libres = 4)")

        post("/reservas/", {"cliente_id": c["1020304050"], "asesor_id": a["AS-01"], "pasajeros": pax(laura),
                            "items": [{"tipo": "hotel", "ref_id": h["coral"], "tipo_hab": "Doble",
                                       "entrada": "2027-01-09", "salida": "2027-01-10", "cantidad": 1}]},
             esperado=409, nota="Sobreventa de hotel")

        antes = get(f"/vuelos/{v['WG7310']}")["tarifas"][0]["libres"]
        post("/reservas/", {"cliente_id": c["1020304050"], "asesor_id": a["AS-01"], "pasajeros": pax(laura, sofia),
                            "items": [{"tipo": "vuelo", "ref_id": v["WG7310"], "tarifa": "Basica", "cantidad": 2},
                                      {"tipo": "hotel", "ref_id": h["coral"], "tipo_hab": "Doble",
                                       "entrada": "2027-01-08", "salida": "2027-01-11", "cantidad": 2}]},
             esperado=409, nota="Vuelo OK + hotel lleno")
        despues = get(f"/vuelos/{v['WG7310']}")["tarifas"][0]["libres"]
        assert antes == despues == 2, (antes, despues)
        print(f"  [ok] Compensación: las sillas del WG7310 siguen en {despues} (se descontaron y se devolvieron)")

        post("/reservas/", {"cliente_id": c["1020304050"], "asesor_id": a["AS-01"], "pasajeros": pax(laura),
                            "items": [{"tipo": "vuelo", "ref_id": v["WG7310"], "tarifa": "Basica", "cantidad": 3}]},
             esperado=409, nota="Sobreventa de vuelo")
        post(f"/reservas/{r1['codigo']}/pagos", {"valor": 5000000, "medio": "PSE", "usuario": "AS-01"},
             esperado=400, nota="Sobrepago")
        post(f"/reservas/{r3['codigo']}/pagos", {"valor": 1000, "medio": "PSE", "usuario": "AS-01"},
             esperado=400, nota="Pago a reserva cancelada")
        post(f"/reservas/{r3['codigo']}/cancelar", {"usuario": "AS-01"}, esperado=400, nota="Doble cancelación")
        post(f"/reservas/{r4['codigo']}/pagos", {"valor": 1000, "medio": "PSE", "usuario": "AS-03"},
             esperado=400, nota="Asesor inactivo")
        post("/vuelos/", {"codigo": "XX1", "aerolinea": "X", "origen": "BOG", "destino": "CTG",
                          "sale": "2026-12-01T10:00:00Z", "llega": "2026-12-01T11:00:00Z",
                          "tarifas": [{"nombre": "Basica", "precio": 1, "equipaje": "x", "sillas": 1, "libres": 999}]},
             esperado=422, nota="Cliente intenta fijar 'libres'")

        print("\nResumen")
        db = client[DB_NAME]
        for col in ["ciudades", "vuelos", "hoteles", "noches", "tours", "salidas",
                    "paquetes", "clientes", "asesores", "reservas"]:
            print(f"  {col:<9} {db[col].count_documents({}):>5}")
        print("\nListo. Levanta la API con:  cd back && uvicorn main:app --reload  ->  http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
