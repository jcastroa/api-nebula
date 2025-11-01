"""
Pydantic schemas for medio_pago (payment methods) endpoints.
Validates request/response data for payment method management.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ===== Request Models =====

class MedioPagoCreateRequest(BaseModel):
    """Request body for creating a new payment method"""
    descripcion: str = Field(..., min_length=1, max_length=100, description="Payment method description")
    detalle: str = Field(..., min_length=1, description="Payment method details")
    nombre_titular: Optional[str] = Field(None, max_length=200, description="Account holder name")
    numero_cuenta: Optional[str] = Field(None, max_length=100, description="Account number")

    @field_validator('descripcion')
    @classmethod
    def validate_descripcion(cls, v: str) -> str:
        """Validate description is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('La descripción del medio de pago es requerida')
        return v.strip()

    @field_validator('detalle')
    @classmethod
    def validate_detalle(cls, v: str) -> str:
        """Validate details are not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('El detalle del medio de pago es requerido')
        return v.strip()


class MedioPagoUpdateRequest(BaseModel):
    """Request body for updating an existing payment method"""
    descripcion: Optional[str] = Field(None, min_length=1, max_length=100, description="Payment method description")
    detalle: Optional[str] = Field(None, min_length=1, description="Payment method details")
    nombre_titular: Optional[str] = Field(None, max_length=200, description="Account holder name")
    numero_cuenta: Optional[str] = Field(None, max_length=100, description="Account number")

    @field_validator('descripcion')
    @classmethod
    def validate_descripcion(cls, v: Optional[str]) -> Optional[str]:
        """Validate description if provided"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError('La descripción del medio de pago no puede estar vacía')
        return v.strip() if v else v

    @field_validator('detalle')
    @classmethod
    def validate_detalle(cls, v: Optional[str]) -> Optional[str]:
        """Validate details if provided"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError('El detalle del medio de pago no puede estar vacío')
        return v.strip() if v else v


# ===== Response Models =====

class MedioPagoResponse(BaseModel):
    """Response with payment method details"""
    id: int = Field(..., description="Payment method ID")
    negocio_id: int = Field(..., description="Business ID")
    descripcion: str = Field(..., description="Payment method description")
    detalle: str = Field(..., description="Payment method details")
    nombre_titular: Optional[str] = Field(None, description="Account holder name")
    numero_cuenta: Optional[str] = Field(None, description="Account number")
    activo: bool = Field(..., description="Payment method active status")
    eliminado: bool = Field(..., description="Payment method deleted status")
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
                "descripcion": "Tarjeta de Crédito",
                "detalle": "Visa terminada en 1234",
                "nombre_titular": "Juan Pérez",
                "numero_cuenta": "****1234",
                "activo": True,
                "eliminado": False,
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:00",
                "created_by": 1,
                "updated_by": 1
            }
        }


class MedioPagoListResponse(BaseModel):
    """Response with list of payment methods"""
    medios_pago: list[MedioPagoResponse] = Field(..., description="List of payment methods")
    total: int = Field(..., description="Total number of payment methods")

    class Config:
        json_schema_extra = {
            "example": {
                "medios_pago": [
                    {
                        "id": 1,
                        "negocio_id": 123,
                        "descripcion": "Tarjeta de Crédito",
                        "detalle": "Visa terminada en 1234",
                        "nombre_titular": "Juan Pérez",
                        "numero_cuenta": "****1234",
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


class MedioPagoSaveResponse(BaseModel):
    """Response after saving/updating a payment method"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: MedioPagoResponse = Field(..., description="Saved payment method data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Medio de pago guardado exitosamente",
                "data": {
                    "id": 1,
                    "negocio_id": 123,
                    "descripcion": "Tarjeta de Crédito",
                    "detalle": "Visa terminada en 1234",
                    "nombre_titular": "Juan Pérez",
                    "numero_cuenta": "****1234",
                    "activo": True,
                    "eliminado": False,
                    "created_at": "2024-01-15T10:30:00",
                    "updated_at": "2024-01-15T10:30:00",
                    "created_by": 1,
                    "updated_by": 1
                }
            }
        }


class MedioPagoDeleteResponse(BaseModel):
    """Response after deleting a payment method"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Medio de pago eliminado exitosamente"
            }
        }
