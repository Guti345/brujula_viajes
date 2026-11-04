"""
app/database.py — Conexión y esquema físico de Brújula Viajes (MongoDB 6+ / PyMongo).

Equivalencias con el database.py de SQLAlchemy:
    engine                      -> MongoClient (pool de conexiones thread-safe, UNO por proceso)
    SessionLocal / get_db()     -> get_db() entrega la Database compartida (no hay sesión por petición)
    Base.metadata.create_all()  -> init_db(): crea colecciones con validador $jsonSchema + índices

Ejecutar una vez desde back/ (idempotente):  python -m app.database
"""
import os

from dotenv import load_dotenv
from pymongo import ASCENDING, GEOSPHERE, IndexModel, MongoClient
from pymongo.database import Database

# ─────────────────────────────── Conexión ───────────────────────────────
load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "brujula_viajes")

# tz_aware=True: las fechas vuelven como datetime con zona UTC (decisión punto 7)
client = MongoClient(MONGO_URL, tz_aware=True, serverSelectionTimeoutMS=5000)
db: Database = client[DB_NAME]


def get_db():
    """Dependencia de FastAPI. No se cierra por petición: el pool vive todo el proceso."""
    yield db


# ─────────────────────── Tipos reutilizables ($jsonSchema) ───────────────────────
STR = {"bsonType": "string"}
DATE = {"bsonType": "date"}
OID = {"bsonType": "objectId"}
BOOL = {"bsonType": "bool"}
NUM_POS = {"bsonType": "number", "minimum": 0}            # precios: number (int/long/double)
INT_POS = {"bsonType": ["int", "long"], "minimum": 0}      # inventarios: nunca negativos
INT_1 = {"bsonType": ["int", "long"], "minimum": 1}
IATA = {"bsonType": "string", "pattern": "^[A-Z]{3}$"}
STR_ARR = {"bsonType": "array", "items": STR}
POINT = {  # GeoJSON Point: [lon, lat]
    "bsonType": "object",
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"enum": ["Point"]},
        "coordinates": {
            "bsonType": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": [
                {"bsonType": "number", "minimum": -180, "maximum": 180},
                {"bsonType": "number", "minimum": -90, "maximum": 90},
            ],
        },
    },
}
TIPOS_HAB = ["Sencilla", "Doble", "Familiar", "Suite"]
TARIFAS = ["Basica", "Clasica", "Flexible"]
ESTADOS = ["Pendiente", "Pagada", "Cancelada"]
MEDIOS = ["Efectivo", "Tarjeta", "Transferencia", "PSE"]


def obj(properties: dict, required: list | None = None) -> dict:
    """Subdocumento. Mongo rechaza 'required: []', por eso solo se agrega si hay campos."""
    schema = {"bsonType": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def unicos(arreglo: str, campo: str) -> dict:
    """$expr: los valores de `campo` dentro de `arreglo` no se repiten (|set| == |array|)."""
    return {
        "$eq": [
            {"$size": {"$setUnion": [{"$ifNull": [campo, []]}]}},
            {"$size": {"$ifNull": [arreglo, []]}},
        ]
    }


def todos(arreglo: str, alias: str, condicion: dict) -> dict:
    """$expr: `condicion` se cumple para cada elemento del arreglo."""
    return {
        "$allElementsTrue": [
            {"$map": {"input": {"$ifNull": [arreglo, []]}, "as": alias, "in": condicion}}
        ]
    }


# ─────────────────────────── Subdocumentos embebidos ───────────────────────────
TARIFA = obj(
    {"nombre": {"enum": TARIFAS}, "precio": NUM_POS, "equipaje": STR,
     "sillas": INT_POS, "libres": INT_POS},
    ["nombre", "precio", "equipaje", "sillas", "libres"],
)

HABITACION = obj(
    {"tipo": {"enum": TIPOS_HAB}, "capacidad": INT_1, "precio_noche": NUM_POS, "cantidad": INT_POS},
    ["tipo", "capacidad", "precio_noche", "cantidad"],
)


def componente(tipo: str, detalle: dict) -> dict:
    return obj(
        {"tipo": {"enum": [tipo]}, "ref_id": OID, "detalle": detalle, "nombre": STR, "precio": NUM_POS},
        ["tipo", "ref_id", "detalle", "nombre", "precio"],
    )


COMPONENTE = {  # detalle polimórfico según tipo
    "oneOf": [
        componente("vuelo", obj({"codigo": STR, "tarifa": {"enum": TARIFAS}}, ["codigo", "tarifa"])),
        componente("hotel", obj(  # 'entrada' agregado en Módulo 0
            {"tipo_hab": {"enum": TIPOS_HAB}, "noches": INT_1, "entrada": DATE},
            ["tipo_hab", "noches", "entrada"],
        )),
        componente("tour", obj({"salida_id": OID}, ["salida_id"])),
    ]
}

ITEM = obj(
    {"tipo": {"enum": ["vuelo", "hotel", "tour", "paquete"]}, "ref_id": OID,
     "detalle": {"bsonType": "object"}, "nombre": STR, "ciudad": IATA,
     "inicio": DATE, "fin": DATE, "cantidad": INT_1, "precio": NUM_POS, "subtotal": NUM_POS},
    ["tipo", "ref_id", "detalle", "nombre", "ciudad", "inicio", "fin", "cantidad", "precio", "subtotal"],
)
PASAJERO = obj({"nombre": STR, "documento": STR, "nacimiento": DATE}, ["nombre", "documento", "nacimiento"])
PAGO = obj({"fecha": DATE, "valor": NUM_POS, "medio": {"enum": MEDIOS}}, ["fecha", "valor", "medio"])
# punto 9: historial.usuario guarda asesores.codigo (ej. "AS-01"); su existencia se valida en el router
EVENTO = obj(
    {"antes": {"enum": ESTADOS + [None]}, "despues": {"enum": ESTADOS}, "fecha": DATE, "usuario": STR},
    ["antes", "despues", "fecha", "usuario"],
)

# ─────────────────────────── Validadores por colección ───────────────────────────
VALIDADORES: dict[str, dict] = {
    "ciudades": {"$jsonSchema": obj({"iata": IATA, "nombre": STR}, ["iata", "nombre"])},

    "vuelos": {"$and": [
        {"$jsonSchema": obj(
            {"codigo": STR, "aerolinea": STR, "origen": IATA, "destino": IATA,
             "sale": DATE, "llega": DATE,
             "tarifas": {"bsonType": "array", "maxItems": 3, "items": TARIFA}},
            ["codigo", "aerolinea", "origen", "destino", "sale", "llega"],
        )},
        {"$expr": {"$and": [
            {"$gt": ["$llega", "$sale"]},
            {"$ne": ["$origen", "$destino"]},
            unicos("$tarifas", "$tarifas.nombre"),                          # punto 11
            todos("$tarifas", "t", {"$lte": ["$$t.libres", "$$t.sillas"]}),
        ]}},
    ]},

    "hoteles": {"$and": [
        {"$jsonSchema": obj(
            {"nombre": STR, "ciudad": IATA, "direccion": STR,
             "estrellas": {"bsonType": ["int", "long"], "minimum": 1, "maximum": 5},
             "servicios": STR_ARR, "ubicacion": POINT,
             "habitaciones": {"bsonType": "array", "maxItems": 4, "items": HABITACION}},
            ["nombre", "ciudad", "direccion", "estrellas"],
        )},
        {"$expr": unicos("$habitaciones", "$habitaciones.tipo")},
    ]},

    "noches": {"$and": [
        {"$jsonSchema": obj(
            {"hotel_id": OID, "tipo": {"enum": TIPOS_HAB}, "fecha": DATE, "libres": INT_POS},
            ["hotel_id", "tipo", "fecha"],  # punto 12: obligatorios, son la llave del índice único
        )},
        # punto 8: la noche se guarda a las 00:00 UTC, si no el índice único admitiría duplicados
        {"$expr": {"$eq": ["$fecha", {"$dateTrunc": {"date": "$fecha", "unit": "day"}}]}},
    ]},

    "tours": {"$jsonSchema": obj(
        {"nombre": STR, "ciudad": IATA, "descripcion": STR, "horas": NUM_POS, "incluye": STR_ARR,
         "encuentro": obj({"lugar": STR, "ubicacion": POINT})},
        ["nombre"],
    )},

    "salidas": {"$and": [
        {"$jsonSchema": obj(
            {"tour_id": OID, "fecha": DATE, "precio": NUM_POS, "cupos": INT_POS, "libres": INT_POS},
            ["tour_id", "fecha"],  # punto 12: obligatorio, es la llave del índice único
        )},
        {"$expr": {"$lte": ["$libres", "$cupos"]}},
    ]},

    "paquetes": {"$and": [
        {"$jsonSchema": obj(
            {"nombre": STR, "destino": IATA,
             "descuento": {"bsonType": "number", "minimum": 0, "maximum": 100},
             "desde": DATE, "hasta": DATE,
             "componentes": {"bsonType": "array", "minItems": 1, "items": COMPONENTE}},
            ["nombre"],
        )},
        {"$expr": {"$or": [
            {"$eq": [{"$type": "$desde"}, "missing"]},
            {"$eq": [{"$type": "$hasta"}, "missing"]},
            {"$lte": ["$desde", "$hasta"]},
        ]}},
    ]},

    "clientes": {"$jsonSchema": obj(
        {"documento": STR, "nombre": STR, "correo": STR, "telefono": STR,
         "preferencias": obj({"favoritos": {"bsonType": "array", "items": IATA},
                              "presupuesto": NUM_POS, "con_ninos": BOOL})},
        ["documento", "nombre", "correo", "telefono"],
    )},

    "asesores": {"$jsonSchema": obj({"codigo": STR, "nombre": STR, "correo": STR, "activo": BOOL})},

    "reservas": {"$and": [
        {"$jsonSchema": obj(
            {"codigo": STR, "cliente_id": OID,
             "cliente": obj({"documento": STR, "nombre": STR}, ["documento", "nombre"]),
             "asesor_id": OID, "asesor": STR, "creada": DATE, "estado": {"enum": ESTADOS},
             "items": {"bsonType": "array", "items": ITEM},
             "pasajeros": {"bsonType": "array", "items": PASAJERO},
             "total": NUM_POS, "pagado": NUM_POS,
             "pagos": {"bsonType": "array", "items": PAGO},
             "historial": {"bsonType": "array", "items": EVENTO}},
            ["codigo", "creada", "estado"],
        )},
        {"$expr": {"$and": [
            {"$eq": ["$total", {"$sum": "$items.subtotal"}]},     # total = Σ subtotales
            {"$eq": ["$pagado", {"$sum": "$pagos.valor"}]},       # pagado = Σ pagos
            {"$lte": ["$pagado", "$total"]},                      # punto 10: sin sobrepago
            todos("$items", "i", {"$and": [
                {"$eq": ["$$i.subtotal", {"$multiply": ["$$i.cantidad", "$$i.precio"]}]},
                {"$lte": ["$$i.inicio", "$$i.fin"]},
            ]}),
        ]}},
    ]},
}

# ─────────────────────────────── Índices ───────────────────────────────
INDICES: dict[str, list[IndexModel]] = {
    "ciudades": [IndexModel([("iata", ASCENDING)], unique=True, name="ux_iata")],
    "vuelos": [
        IndexModel([("codigo", ASCENDING)], unique=True, name="ux_codigo"),
        IndexModel([("origen", ASCENDING), ("destino", ASCENDING), ("sale", ASCENDING)], name="ix_ruta_sale"),
    ],
    "hoteles": [
        IndexModel([("ciudad", ASCENDING)], name="ix_ciudad"),
        IndexModel([("ubicacion", GEOSPHERE)], name="geo_ubicacion"),
    ],
    "noches": [IndexModel([("hotel_id", ASCENDING), ("tipo", ASCENDING), ("fecha", ASCENDING)],
                          unique=True, name="ux_hotel_tipo_fecha")],
    "tours": [
        IndexModel([("ciudad", ASCENDING)], name="ix_ciudad"),
        IndexModel([("encuentro.ubicacion", GEOSPHERE)], name="geo_encuentro"),
    ],
    "salidas": [IndexModel([("tour_id", ASCENDING), ("fecha", ASCENDING)], unique=True, name="ux_tour_fecha")],
    "paquetes": [IndexModel([("destino", ASCENDING), ("hasta", ASCENDING)], name="ix_destino_hasta")],
    "clientes": [IndexModel([("documento", ASCENDING)], unique=True, name="ux_documento")],
    "asesores": [IndexModel([("codigo", ASCENDING)], unique=True, name="ux_codigo")],
    "reservas": [
        IndexModel([("codigo", ASCENDING)], unique=True, name="ux_codigo"),
        IndexModel([("estado", ASCENDING), ("creada", ASCENDING)], name="ix_estado_creada"),
        IndexModel([("items.ciudad", ASCENDING)], name="ix_items_ciudad"),
    ],
}


def init_db(database: Database = db) -> None:
    """Idempotente: crea o actualiza (collMod) validadores y crea los índices que falten."""
    client.admin.command("ping")  # falla rápido si Mongo no está arriba
    existentes = set(database.list_collection_names())
    opciones = {"validationLevel": "strict", "validationAction": "error"}

    for nombre, validador in VALIDADORES.items():
        if nombre in existentes:
            database.command("collMod", nombre, validator=validador, **opciones)
        else:
            database.create_collection(nombre, validator=validador, **opciones)

    for nombre, indices in INDICES.items():
        database[nombre].create_indexes(indices)


if __name__ == "__main__":
    init_db()
    print(f"[ok] {DB_NAME}: {len(VALIDADORES)} colecciones con validador e índices listos.")
