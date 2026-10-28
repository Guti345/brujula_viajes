import enum

# En MongoDB no se definen tablas ni columnas: cada colección guarda documentos
# JSON (BSON) y la forma de esos documentos la validan los schemas de Pydantic.
# Aquí solo quedan los nombres de las colecciones y los enums compartidos.
#
# Ejemplo de documento en la colección "tratamientos":
# {
#     "_id": ObjectId("..."),      <- id interno de Mongo (no se expone en la API)
#     "id": 1,                     <- id entero que usa la API
#     "paciente_id": 3,            <- "llave foránea" (Mongo no la valida)
#     "medico_id": 2,
#     "diagnostico": "Maloclusión clase II",
#     "sesiones_estimadas": 12,
#     "estado": "Activo",
#     "eficacia_calculada": null
# }

PACIENTES = "pacientes"
TRATAMIENTOS = "tratamientos"
PERSONAL_MEDICO = "personal_medico"


class TipoPersonalMedico(str, enum.Enum):
    senior = "senior"
    junior = "junior"
    terapeuta = "terapeuta"
    tecnico = "tecnico"
