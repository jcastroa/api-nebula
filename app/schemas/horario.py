"""
Pydantic schemas for horarios (business hours) endpoints.
Validates request/response data for business hours and exceptions management.
"""

from typing import Optional, Dict, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date, time
from enum import Enum


# ===== Enums =====

class TipoExcepcion(str, Enum):
    """Valid exception types"""
    FERIADO = "feriado"
    VACACIONES = "vacaciones"
    OTRO = "otro"


class DiaSemana(str, Enum):
    """Days of the week"""
    LUNES = "lunes"
    MARTES = "martes"
    MIERCOLES = "miercoles"
    JUEVES = "jueves"
    VIERNES = "viernes"
    SABADO = "sabado"
    DOMINGO = "domingo"


# ===== Helper Models =====

class RangoHorario(BaseModel):
    """Time range for business hours"""
    inicio: str = Field(..., description="Start time (HH:MM)")
    fin: str = Field(..., description="End time (HH:MM)")

    @field_validator('inicio', 'fin')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format is HH:MM"""
        if not v:
            raise ValueError('La hora es requerida')

        try:
            # Validate format HH:MM
            time_parts = v.split(':')
            if len(time_parts) != 2:
                raise ValueError('El formato debe ser HH:MM')

            hours, minutes = int(time_parts[0]), int(time_parts[1])

            if hours < 0 or hours > 23:
                raise ValueError('Las horas deben estar entre 00 y 23')

            if minutes < 0 or minutes > 59:
                raise ValueError('Los minutos deben estar entre 00 y 59')

            # Return formatted time
            return f"{hours:02d}:{minutes:02d}"

        except (ValueError, AttributeError):
            raise ValueError(f'Formato de hora inválido: {v}. Use HH:MM')

    def model_post_init(self, __context):
        """Validate that inicio is before fin"""
        if self.inicio >= self.fin:
            raise ValueError('La hora de inicio debe ser anterior a la hora de fin')


# ===== Request Models - Horarios =====

class HorariosCreateRequest(BaseModel):
    """Request body for creating/updating business hours"""
    dias_laborables: Dict[str, bool] = Field(
        ...,
        description="Working days map (e.g., {'lunes': true, 'martes': false, ...})"
    )
    horarios: Dict[str, List[RangoHorario]] = Field(
        ...,
        description="Business hours per day (e.g., {'lunes': [{'inicio': '09:00', 'fin': '13:00'}], ...})"
    )
    intervalo_citas: int = Field(
        ...,
        ge=15,
        description="Appointment interval in minutes (15, 30, 45, 60, 90, 120)"
    )

    @field_validator('intervalo_citas')
    @classmethod
    def validate_intervalo_citas(cls, v: int) -> int:
        """Validate appointment interval is in valid range"""
        valid_intervals = [15, 30, 45, 60, 90, 120]
        if v not in valid_intervals:
            raise ValueError(f'El intervalo de citas debe ser uno de: {", ".join(map(str, valid_intervals))}')
        return v

    @field_validator('dias_laborables')
    @classmethod
    def validate_dias_laborables(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        """Validate all days are present"""
        required_days = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

        for day in required_days:
            if day not in v:
                raise ValueError(f'Falta el día: {day}')

        return v

    @field_validator('horarios')
    @classmethod
    def validate_horarios(cls, v: Dict[str, List[RangoHorario]]) -> Dict[str, List[RangoHorario]]:
        """Validate all days are present in horarios"""
        required_days = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

        for day in required_days:
            if day not in v:
                raise ValueError(f'Falta el día en horarios: {day}')

            # Validate time ranges don't overlap
            if len(v[day]) > 1:
                sorted_ranges = sorted(v[day], key=lambda x: x.inicio)
                for i in range(len(sorted_ranges) - 1):
                    if sorted_ranges[i].fin > sorted_ranges[i + 1].inicio:
                        raise ValueError(f'Los horarios del {day} se superponen')

        return v


# ===== Request Models - Excepciones =====

class ExcepcionCreateRequest(BaseModel):
    """Request body for creating an exception (non-working day)"""
    tipo: TipoExcepcion = Field(..., description="Exception type (feriado, vacaciones, otro)")
    fechaInicio: date = Field(..., description="Start date (YYYY-MM-DD)")
    fechaFin: Optional[date] = Field(None, description="End date (YYYY-MM-DD), optional for single day")
    motivo: str = Field(..., min_length=1, max_length=500, description="Reason for the exception")

    @field_validator('fechaFin', mode='before')
    @classmethod
    def validate_fecha_fin(cls, v):
        """Convert empty string to None for optional date field"""
        if v == "" or v is None:
            return None
        return v

    @field_validator('motivo')
    @classmethod
    def validate_motivo(cls, v: str) -> str:
        """Validate motivo is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('El motivo es requerido')
        return v.strip()

    def model_post_init(self, __context):
        """Validate fechaFin is after or equal to fechaInicio"""
        if self.fechaFin and self.fechaInicio > self.fechaFin:
            raise ValueError('La fecha de inicio debe ser anterior o igual a la fecha de fin')


# ===== Response Models - Horarios =====

class HorariosResponse(BaseModel):
    """Response with business hours configuration"""
    dias_laborables: Dict[str, bool] = Field(..., description="Working days configuration")
    horarios: Dict[str, List[RangoHorario]] = Field(..., description="Business hours per day")
    intervalo_citas: int = Field(..., description="Appointment interval in minutes")

    class Config:
        json_schema_extra = {
            "example": {
                "dias_laborables": {
                    "lunes": True,
                    "martes": True,
                    "miercoles": True,
                    "jueves": True,
                    "viernes": True,
                    "sabado": False,
                    "domingo": False
                },
                "horarios": {
                    "lunes": [
                        {"inicio": "09:00", "fin": "13:00"},
                        {"inicio": "16:00", "fin": "22:00"}
                    ],
                    "martes": [
                        {"inicio": "08:00", "fin": "12:00"},
                        {"inicio": "14:00", "fin": "18:00"}
                    ],
                    "miercoles": [{"inicio": "09:00", "fin": "18:00"}],
                    "jueves": [{"inicio": "09:00", "fin": "18:00"}],
                    "viernes": [{"inicio": "09:00", "fin": "18:00"}],
                    "sabado": [{"inicio": "09:00", "fin": "13:00"}],
                    "domingo": [{"inicio": "09:00", "fin": "13:00"}]
                },
                "intervalo_citas": 30
            }
        }


class HorariosSaveResponse(BaseModel):
    """Response after saving business hours"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Configuración guardada exitosamente"
            }
        }


# ===== Response Models - Excepciones =====

class ExcepcionResponse(BaseModel):
    """Response with exception details"""
    id: int = Field(..., description="Exception ID")
    tipo: str = Field(..., description="Exception type")
    fecha_inicio: date = Field(..., description="Start date")
    fecha_fin: Optional[date] = Field(None, description="End date")
    motivo: str = Field(..., description="Reason for the exception")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "tipo": "feriado",
                "fecha_inicio": "2024-12-25",
                "fecha_fin": "2024-12-25",
                "motivo": "Navidad"
            }
        }


class ExcepcionesListResponse(BaseModel):
    """Response with list of exceptions"""
    excepciones: List[ExcepcionResponse] = Field(..., description="List of exceptions")

    class Config:
        json_schema_extra = {
            "example": {
                "excepciones": [
                    {
                        "id": 1,
                        "tipo": "feriado",
                        "fecha_inicio": "2024-12-25",
                        "fecha_fin": "2024-12-25",
                        "motivo": "Navidad"
                    },
                    {
                        "id": 2,
                        "tipo": "vacaciones",
                        "fecha_inicio": "2024-07-01",
                        "fecha_fin": "2024-07-15",
                        "motivo": "Vacaciones de verano"
                    }
                ]
            }
        }


class ExcepcionSaveResponse(BaseModel):
    """Response after saving an exception"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")
    excepcion: ExcepcionResponse = Field(..., description="Created exception data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Excepción agregada exitosamente",
                "excepcion": {
                    "id": 3,
                    "tipo": "feriado",
                    "fecha_inicio": "2024-12-25",
                    "fecha_fin": "2024-12-25",
                    "motivo": "Navidad"
                }
            }
        }


class ExcepcionDeleteResponse(BaseModel):
    """Response after deleting an exception"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Excepción eliminada exitosamente"
            }
        }
