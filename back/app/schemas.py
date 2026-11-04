"""
app/schemas.py — DTOs (Pydantic v2) de Brújula Viajes.

Convenciones:
  * XxxCreate  -> lo que ENVÍA el cliente. extra="forbid": no puede colar campos que calcula
                  el servidor (libres, precio congelado, subtotal, total, estado, historial...).
  * XxxResponse-> lo que DEVUELVE la API. Lee el documento de Mongo tal cual (`_id` -> `id`).
  * Los ObjectId viajan como texto de 24 hex; el router los convierte con ObjectId(...).
  * Fechas con hora (vuelos, salidas): datetime CON zona horaria (AwareDatetime). Se guardan en UTC.
  * Fechas de día (noches, entrada de hotel, nacimiento, vigencias): `date`. El router las
    convierte a 00:00 UTC antes de guardar, porque BSON no tiene un tipo "solo fecha".
  * Precios: number (float en Python, double en Mongo).
"""
from datetime import date, datetime
from typing import Annotated, Any, Literal, Union

from bson import ObjectId
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

# ─────────────────────────────── Tipos base ───────────────────────────────
TipoHab = Literal["Sencilla", "Doble", "Familiar", "Suite"]
NombreTarifa = Literal["Basica", "Clasica", "Flexible"]
Estado = Literal["Pendiente", "Pagada", "Cancelada"]
Medio = Literal["Efectivo", "Tarjeta", "Transferencia", "PSE"]

Iata = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["CTG"])]
Dinero = Annotated[int, Field(ge=0)]          # pesos COP enteros (ver nota de sumas exactas)
Numero = int | float                          # salida: conserva el tipo guardado
EnteroPos = Annotated[int, Field(ge=0)]
Texto = Annotated[str, Field(min_length=1)]


def _validar_oid(v: str) -> str:
    if not ObjectId.is_valid(v):
        raise ValueError("ObjectId inválido (se esperan 24 caracteres hexadecimales)")
    return v


def _limpiar(v: Any) -> Any:
    """Convierte recursivamente ObjectId -> str para poder serializar a JSON."""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, dict):
        return {k: _limpiar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_limpiar(x) for x in v]
    return v


OidIn = Annotated[str, AfterValidator(_validar_oid)]     # entrada: texto validado
OidOut = Annotated[str, BeforeValidator(str)]            # salida: ObjectId -> texto
Detalle = Annotated[dict[str, Any], BeforeValidator(_limpiar)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Salida(BaseModel):
    # validation_alias: lee "_id" desde Mongo pero serializa como "id" en el JSON
    model_config = ConfigDict(populate_by_name=True)
    id: OidOut = Field(validation_alias="_id")


def _sin_repetidos(valores: list, que: str) -> None:
    if len(valores) != len(set(valores)):
        raise ValueError(f"{que} repetido")


# ─────────────────────────────── GeoJSON ───────────────────────────────
class Punto(Entrada):
    type: Literal["Point"] = "Point"
    coordinates: tuple[
        Annotated[float, Field(ge=-180, le=180)],   # longitud
        Annotated[float, Field(ge=-90, le=90)],     # latitud
    ]


# ─────────────────────────────── ciudades ───────────────────────────────
class CiudadCreate(Entrada):
    iata: Iata
    nombre: Texto


class CiudadResponse(Salida):
    iata: str
    nombre: str


# ─────────────────────────────── vuelos ───────────────────────────────
class TarifaCreate(Entrada):
    nombre: NombreTarifa
    precio: Dinero
    equipaje: Texto
    sillas: EnteroPos          # libres = sillas lo asigna el servidor al crear


class TarifaResponse(BaseModel):
    nombre: NombreTarifa
    precio: Numero
    equipaje: str
    sillas: int
    libres: int


class VueloCreate(Entrada):
    codigo: Texto
    aerolinea: Texto
    origen: Iata
    destino: Iata
    sale: AwareDatetime
    llega: AwareDatetime
    tarifas: list[TarifaCreate] = Field(min_length=1, max_length=3)     # "una o más tarifas"

    @model_validator(mode="after")
    def _coherencia(self):
        if self.origen == self.destino:
            raise ValueError("origen y destino deben ser distintos")
        if self.llega <= self.sale:
            raise ValueError("llega debe ser posterior a sale")
        _sin_repetidos([t.nombre for t in self.tarifas], "nombre de tarifa")
        return self


class VueloResponse(Salida):
    codigo: str
    aerolinea: str
    origen: str
    destino: str
    sale: datetime
    llega: datetime
    tarifas: list[TarifaResponse] = []


# ─────────────────────────────── hoteles ───────────────────────────────
class Habitacion(Entrada):
    tipo: TipoHab
    capacidad: Annotated[int, Field(ge=1)]
    precio_noche: Dinero
    cantidad: EnteroPos


class HotelCreate(Entrada):
    nombre: Texto
    ciudad: Iata
    direccion: Texto
    estrellas: Annotated[int, Field(ge=1, le=5)]
    servicios: list[Texto] = Field(default_factory=list)
    ubicacion: Punto | None = None
    habitaciones: list[Habitacion] = Field(min_length=1, max_length=4)

    @field_validator("habitaciones")
    @classmethod
    def _tipos_unicos(cls, v):
        _sin_repetidos([h.tipo for h in v], "tipo de habitación")
        return v


class HotelResponse(Salida):
    nombre: str
    ciudad: str
    direccion: str
    estrellas: int
    servicios: list[str] = []
    ubicacion: dict | None = None
    habitaciones: list[dict] = []


# ─────────────────────────────── noches (punto 6) ───────────────────────────────
class NochesGenerar(Entrada):
    """POST /hoteles/{id}/noches — crea las noches [desde, hasta) con libres = cantidad (upsert)."""
    desde: date
    hasta: date
    tipos: list[TipoHab] | None = None     # None = todos los tipos del hotel

    @model_validator(mode="after")
    def _rango(self):
        if self.hasta <= self.desde:
            raise ValueError("hasta debe ser posterior a desde")
        if (self.hasta - self.desde).days > 366:
            raise ValueError("máximo 366 noches por solicitud")
        return self


class NochesGeneradas(BaseModel):
    creadas: int
    existentes: int               # ya estaban: no se tocan (decisión punto 6)


class NocheResponse(Salida):
    hotel_id: OidOut
    tipo: TipoHab
    fecha: datetime
    libres: int


# ─────────────────────────────── tours y salidas ───────────────────────────────
class Encuentro(Entrada):
    lugar: Texto
    ubicacion: Punto | None = None


class TourCreate(Entrada):
    nombre: Texto
    ciudad: Iata | None = None
    descripcion: str | None = None
    horas: Annotated[float, Field(ge=0)] | None = None
    incluye: list[Texto] = Field(default_factory=list)
    encuentro: Encuentro | None = None


class TourResponse(Salida):
    nombre: str
    ciudad: str | None = None
    descripcion: str | None = None
    horas: float | None = None
    incluye: list[str] = []
    encuentro: dict | None = None


class SalidaCreate(Entrada):
    tour_id: OidIn
    fecha: AwareDatetime
    precio: Dinero                # por persona
    cupos: EnteroPos              # libres = cupos lo asigna el servidor


class SalidaResponse(Salida):
    tour_id: OidOut
    fecha: datetime
    precio: Numero
    cupos: int
    libres: int


# ─────────────────────────────── paquetes ───────────────────────────────
# El cliente solo dice QUÉ incluye; nombre, precio y codigo los COPIA el servidor (REF + COPIA).
class DetalleVueloIn(Entrada):
    tarifa: NombreTarifa


class DetalleHotelIn(Entrada):
    tipo_hab: TipoHab
    noches: Annotated[int, Field(ge=1)]
    entrada: date                 # agregado en Módulo 0


class DetalleTourIn(Entrada):
    salida_id: OidIn


class CompVueloIn(Entrada):
    tipo: Literal["vuelo"]
    ref_id: OidIn                 # vuelos._id
    detalle: DetalleVueloIn


class CompHotelIn(Entrada):
    tipo: Literal["hotel"]
    ref_id: OidIn                 # hoteles._id
    detalle: DetalleHotelIn


class CompTourIn(Entrada):
    tipo: Literal["tour"]
    ref_id: OidIn                 # tours._id (la salida va en detalle.salida_id)
    detalle: DetalleTourIn


ComponenteIn = Annotated[Union[CompVueloIn, CompHotelIn, CompTourIn], Field(discriminator="tipo")]


class PaqueteCreate(Entrada):
    nombre: Texto
    destino: Iata
    descuento: Annotated[float, Field(ge=0, le=100)] = 0
    desde: date                   # ventana de VENTA (decisión punto 4)
    hasta: date
    componentes: list[ComponenteIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _ventana(self):
        if self.hasta < self.desde:
            raise ValueError("hasta no puede ser anterior a desde")
        return self


class ComponenteResponse(BaseModel):
    tipo: Literal["vuelo", "hotel", "tour"]
    ref_id: OidOut
    detalle: Detalle
    nombre: str
    precio: Numero                 # por persona


class PaqueteResponse(Salida):
    nombre: str
    destino: str
    descuento: float = 0
    desde: datetime | None = None
    hasta: datetime | None = None
    componentes: list[ComponenteResponse] = []


# ─────────────────────────────── clientes y asesores ───────────────────────────────
class Preferencias(Entrada):
    favoritos: list[Iata] = Field(default_factory=list)
    presupuesto: Dinero | None = None
    con_ninos: bool = False


class ClienteCreate(Entrada):
    documento: Annotated[str, Field(min_length=5, max_length=20)]
    nombre: Texto
    correo: EmailStr
    telefono: Annotated[str, Field(min_length=7, max_length=15)]
    preferencias: Preferencias | None = None


class ClienteResponse(Salida):
    documento: str
    nombre: str
    correo: str
    telefono: str
    preferencias: dict | None = None


class AsesorCreate(Entrada):
    codigo: Texto
    nombre: Texto
    correo: EmailStr
    activo: bool = True


class AsesorResponse(Salida):
    codigo: str
    nombre: str
    correo: str
    activo: bool = True


# ─────────────────────────────── reservas ───────────────────────────────
# Entrada mínima: el servidor calcula nombre, ciudad, inicio, fin, precio (congelado) y subtotal.
class ItemVueloIn(Entrada):
    tipo: Literal["vuelo"]
    ref_id: OidIn
    tarifa: NombreTarifa
    cantidad: Annotated[int, Field(ge=1)]           # sillas


class ItemHotelIn(Entrada):
    tipo: Literal["hotel"]
    ref_id: OidIn
    tipo_hab: TipoHab
    entrada: date
    salida: date                                    # noches = [entrada, salida)
    cantidad: Annotated[int, Field(ge=1)]           # personas -> ceil(personas/capacidad) habitaciones

    @model_validator(mode="after")
    def _rango(self):
        if self.salida <= self.entrada:
            raise ValueError("salida debe ser posterior a entrada")
        return self


class ItemTourIn(Entrada):
    tipo: Literal["tour"]
    ref_id: OidIn                                   # tours._id
    salida_id: OidIn
    cantidad: Annotated[int, Field(ge=1)]           # cupos


class ItemPaqueteIn(Entrada):
    tipo: Literal["paquete"]
    ref_id: OidIn
    cantidad: Annotated[int, Field(ge=1)]           # personas


ItemIn = Annotated[
    Union[ItemVueloIn, ItemHotelIn, ItemTourIn, ItemPaqueteIn], Field(discriminator="tipo")
]


class Pasajero(Entrada):
    nombre: Texto
    documento: Texto
    nacimiento: date


class ReservaCreate(Entrada):
    cliente_id: OidIn
    asesor_id: OidIn
    items: list[ItemIn] = Field(min_length=1, max_length=20)
    pasajeros: list[Pasajero] = Field(min_length=1, max_length=20)

    @field_validator("pasajeros")
    @classmethod
    def _documentos_unicos(cls, v):
        _sin_repetidos([p.documento for p in v], "documento de pasajero")
        return v


class PagoCreate(Entrada):
    valor: Annotated[int, Field(gt=0)]              # el tope (saldo) lo valida el router + Mongo
    medio: Medio
    usuario: Texto                                  # asesores.codigo (punto 9)


class CancelarReserva(Entrada):
    usuario: Texto                                  # asesores.codigo (punto 9)


class ItemResponse(BaseModel):
    tipo: Literal["vuelo", "hotel", "tour", "paquete"]
    ref_id: OidOut
    detalle: Detalle
    nombre: str
    ciudad: str
    inicio: datetime
    fin: datetime
    cantidad: int
    precio: Numero
    subtotal: Numero


class PagoResponse(BaseModel):
    fecha: datetime
    valor: Numero
    medio: Medio


class EventoResponse(BaseModel):
    antes: Estado | None
    despues: Estado
    fecha: datetime
    usuario: str


class ClienteCopia(BaseModel):
    documento: str
    nombre: str


class ReservaResponse(Salida):
    codigo: str
    cliente_id: OidOut
    cliente: ClienteCopia
    asesor_id: OidOut
    asesor: str
    creada: datetime
    estado: Estado
    items: list[ItemResponse]
    pasajeros: list[dict]
    total: Numero
    pagado: Numero
    saldo: Numero = 0                                # calculado al leer, NO se guarda

    pagos: list[PagoResponse] = []
    historial: list[EventoResponse] = []

    @model_validator(mode="after")
    def _saldo(self):
        self.saldo = self.total - self.pagado
        return self


class Mensaje(BaseModel):
    detail: str


# ─────────────────── Actualizaciones parciales (PATCH) ───────────────────
# Solo campos que NO son inventario: tarifas, habitaciones, cupos y componentes no se editan
# por API, porque reemplazarlos reiniciaría el inventario vendido (decisión Módulo 2, punto 5).
class HotelUpdate(Entrada):
    nombre: Texto | None = None
    direccion: Texto | None = None
    estrellas: Annotated[int, Field(ge=1, le=5)] | None = None
    servicios: list[Texto] | None = None
    ubicacion: Punto | None = None


class TourUpdate(Entrada):
    nombre: Texto | None = None
    descripcion: str | None = None
    horas: Annotated[float, Field(ge=0)] | None = None
    incluye: list[Texto] | None = None
    encuentro: Encuentro | None = None


class ClienteUpdate(Entrada):
    nombre: Texto | None = None
    correo: EmailStr | None = None
    telefono: Annotated[str, Field(min_length=7, max_length=15)] | None = None
    preferencias: Preferencias | None = None


class AsesorUpdate(Entrada):
    nombre: Texto | None = None
    correo: EmailStr | None = None
    activo: bool | None = None


# ─────────────────── Consulta de disponibilidad hotelera ───────────────────
class DisponibilidadResponse(BaseModel):
    hotel_id: str
    tipo: TipoHab
    personas: int
    habitaciones: int             # ceil(personas / capacidad)
    noches: int
    disponible: bool
    faltan: list[date]            # noches sin cupo o sin generar (el modelo pide reportar cuál)


# ─────────────────────────────── reportes (B1-B3) ───────────────────────────────
class VentasMes(BaseModel):
    anio: int
    mes: int
    total_vendido: Numero
    reservas: int


class DestinoVendido(BaseModel):
    ciudad: str
    ingresos: Numero
    pasajeros: int                # interpretación por ítems, ver routers/reportes.py


class OcupacionVuelo(BaseModel):
    codigo: str
    sillas_totales: int
    vendidas: int
    ocupacion_pct: float
