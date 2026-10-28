from datetime import date, datetime

from pymongo import MongoClient, ReturnDocument

MONGO_URL = "mongodb://localhost:27017"
DATABASE_NAME = "orthoconnect_db"

# MongoClient maneja internamente un pool de conexiones,
# por eso se crea una sola vez para toda la aplicación.
client = MongoClient(MONGO_URL)
db = client[DATABASE_NAME]


def get_db():
    # Se mantiene la misma firma que con SQLAlchemy para usarlo con Depends().
    # No hay sesión que cerrar: el cliente vive mientras viva la aplicación.
    yield db


def siguiente_id(nombre_coleccion: str) -> int:
    # MongoDB no tiene columnas autoincrementales como PostgreSQL (SERIAL).
    # Se simulan con una colección "counters" que guarda el último id usado
    # por cada colección. $inc es atómico, así que no se repiten ids.
    contador = db["counters"].find_one_and_update(
        {"_id": nombre_coleccion},
        {"$inc": {"valor": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return contador["valor"]


def a_documento(datos: dict) -> dict:
    # BSON no soporta datetime.date (solo datetime), así que se convierte al guardar.
    return {
        campo: datetime(valor.year, valor.month, valor.day)
        if isinstance(valor, date) and not isinstance(valor, datetime)
        else valor
        for campo, valor in datos.items()
    }


def referencias_inexistentes(datos: dict, referencias: dict) -> list:
    # MongoDB no tiene ForeignKey, así que la integridad referencial se valida a mano.
    # referencias = {"campo_en_datos": "coleccion_referenciada"}
    # Devuelve los campos cuyo id no existe en la colección referenciada.
    #
    # $documents crea un documento "virtual" con los datos que se quieren guardar
    # y $lookup lo cruza contra cada colección (como un LEFT JOIN en SQL).
    # Si el arreglo resultante queda vacío, la referencia no existe.
    campos = [campo for campo in referencias if datos.get(campo) is not None]
    if not campos:
        return []

    pipeline = [{"$documents": [{campo: datos[campo] for campo in campos}]}]
    for campo in campos:
        pipeline.append({
            "$lookup": {
                "from": referencias[campo],
                "localField": campo,
                "foreignField": "id",
                "as": f"{campo}_encontrado",
                "pipeline": [{"$project": {"_id": 1}}],  # solo importa si existe
            }
        })

    resultado = next(db.aggregate(pipeline))
    return [campo for campo in campos if not resultado[f"{campo}_encontrado"]]


def crear_indices():
    # Equivalente a primary_key=True, index=True: el campo "id" debe ser único.
    for coleccion in ("pacientes", "tratamientos", "personal_medico"):
        db[coleccion].create_index("id", unique=True)
