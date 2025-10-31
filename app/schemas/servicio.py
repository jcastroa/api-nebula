"""
Pydantic schemas for servicio (services) endpoints.
Validates request/response data for service management.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from decimal import Decimal


# ===== Request Models =====

class ServicioCreateRequest(BaseModel):
    """Request body for creating a new service"""
    nombre: str = Field(..., min_length=1, max_length=100, description="Service name")
    descripcion: Optional[str] = Field(None, max_length=1000, description="Service description")
    duracion_minutos: int = Field(30, ge=1, le=1440, description="Service duration in minutes (1-1440)")
    precio: Decimal = Field(..., ge=0, description="Service price")
    activo: bool = Field(True, description="Service active status")

    @field_validator('nombre')
    @classmethod
    def validate_nombre(cls, v: str) -> str:
        """Validate service name is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('El nombre del servicio es requerido')
        return v.strip()

    @field_validator('precio')
    @classmethod
    def validate_precio(cls, v: Decimal) -> Decimal:
        """Validate price is non-negative and has correct precision"""
        if v < 0:
            raise ValueError('El precio no puede ser negativo')

        # Validate max_digits (10 total digits)
        # Convert to string to check total digits
        price_str = str(v)
        # Remove decimal point and minus sign for counting
        digits_only = price_str.replace('.', '').replace('-', '')
        if len(digits_only) > 10:
            raise ValueError('El precio no puede tener más de 10 dígitos en total')

        # Validate decimal_places (2 decimal places)
        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            if len(decimal_part) > 2:
                raise ValueError('El precio no puede tener más de 2 decimales')

        return v


class ServicioUpdateRequest(BaseModel):
    """Request body for updating an existing service"""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100, description="Service name")
    descripcion: Optional[str] = Field(None, max_length=1000, description="Service description")
    duracion_minutos: Optional[int] = Field(None, ge=1, le=1440, description="Service duration in minutes")
    precio: Optional[Decimal] = Field(None, ge=0, description="Service price")
    activo: Optional[bool] = Field(None, description="Service active status")

    @field_validator('nombre')
    @classmethod
    def validate_nombre(cls, v: Optional[str]) -> Optional[str]:
        """Validate service name if provided"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError('El nombre del servicio no puede estar vacío')
        return v.strip() if v else v

    @field_validator('precio')
    @classmethod
    def validate_precio(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price is non-negative and has correct precision if provided"""
        if v is None:
            return v

        if v < 0:
            raise ValueError('El precio no puede ser negativo')

        # Validate max_digits (10 total digits)
        price_str = str(v)
        digits_only = price_str.replace('.', '').replace('-', '')
        if len(digits_only) > 10:
            raise ValueError('El precio no puede tener más de 10 dígitos en total')

        # Validate decimal_places (2 decimal places)
        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            if len(decimal_part) > 2:
                raise ValueError('El precio no puede tener más de 2 decimales')

        return v


# ===== Response Models =====

class ServicioResponse(BaseModel):
    """Response with service details"""
    id: int = Field(..., description="Service ID")
    negocio_id: int = Field(..., description="Business ID")
    nombre: str = Field(..., description="Service name")
    descripcion: Optional[str] = Field(None, description="Service description")
    duracion_minutos: int = Field(..., description="Service duration in minutes")
    precio: Decimal = Field(..., description="Service price")
    activo: bool = Field(..., description="Service active status")
    eliminado: bool = Field(..., description="Service deleted status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    created_by: Optional[int] = Field(None, description="Creator user ID")
    updated_by: Optional[int] = Field(None, description="Last updater user ID")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "negocio_id": 123,
                "nombre": "Consulta General",
                "descripcion": "Consulta médica general",
                "duracion_minutos": 30,
                "precio": 100.00,
                "activo": True,
                "eliminado": False,
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:00",
                "created_by": 1,
                "updated_by": 1
            }
        }


class ServicioListResponse(BaseModel):
    """Response with list of services"""
    servicios: list[ServicioResponse] = Field(..., description="List of services")
    total: int = Field(..., description="Total number of services")

    class Config:
        json_schema_extra = {
            "example": {
                "servicios": [
                    {
                        "id": 1,
                        "negocio_id": 123,
                        "nombre": "Consulta General",
                        "descripcion": "Consulta médica general",
                        "duracion_minutos": 30,
                        "precio": 100.00,
                        "activo": True,
                        "eliminado": False,
                        "created_at": "2024-01-15T10:30:00",
                        "updated_at": "2024-01-15T10:30:00",
                        "created_by": 1,
                        "updated_by": 1
                    }
                ],
                "total": 1
            }
        }


class ServicioSaveResponse(BaseModel):
    """Response after saving/updating a service"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: ServicioResponse = Field(..., description="Saved service data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Servicio guardado exitosamente",
                "data": {
                    "id": 1,
                    "negocio_id": 123,
                    "nombre": "Consulta General",
                    "descripcion": "Consulta médica general",
                    "duracion_minutos": 30,
                    "precio": 100.00,
                    "activo": True,
                    "eliminado": False,
                    "created_at": "2024-01-15T10:30:00",
                    "updated_at": "2024-01-15T10:30:00",
                    "created_by": 1,
                    "updated_by": 1
                }
            }
        }


class ServicioDeleteResponse(BaseModel):
    """Response after deleting a service"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Servicio eliminado exitosamente"
            }
        }
