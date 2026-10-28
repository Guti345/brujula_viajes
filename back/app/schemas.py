from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from .models import TipoPersonalMedico


class PacienteBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100)
    fecha_nacimiento: date
    contacto: str
    referido_por_id: Optional[int] = None

#No se agrega nada nuevo, pero se mantiene la estructura para futuras modificaciones
class PacienteCreate(PacienteBase):
    pass


class PacienteResponse(PacienteBase):
    id: int

    class Config:
        from_attributes = True


class TratamientoBase(BaseModel):
    paciente_id: int
    medico_id: int
    diagnostico: str
    sesiones_estimadas: int = Field(..., gt=0)


class TratamientoCreate(TratamientoBase):
    pass


class TratamientoResponse(TratamientoBase):
    id: int
    estado: str
    eficacia_calculada: Optional[float] = None

    class Config:
        from_attributes = True


class PersonalMedicoBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100)
    especialidad: str
    tipo: TipoPersonalMedico = TipoPersonalMedico.senior
    jefe_id: Optional[int] = None


class PersonalMedicoCreate(PersonalMedicoBase):
    pass


class PersonalMedicoResponse(PersonalMedicoBase):
    id: int

    class Config:
        from_attributes = True


# Respuesta con los datos "unidos" mediante $lookup (paciente y médico embebidos)
class TratamientoDetalleResponse(TratamientoResponse):
    paciente: Optional[PacienteResponse] = None
    medico: Optional[PersonalMedicoResponse] = None
