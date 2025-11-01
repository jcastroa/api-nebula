"""
Pydantic schemas for promocion (promotions) endpoints.
Validates request/response data for promotion management.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


# ===== Enums =====

class TipoDescuento(str, Enum):
    """Promotion discount type"""
    PORCENTAJE = "porcentaje"
    MONTO_FIJO = "monto_fijo"


# ===== Request Models =====

class PromocionCreateRequest(BaseModel):
    """Request body for creating a new promotion"""
    titulo: str = Field(..., min_length=1, max_length=150, description="Promotion title")
    descripcion: str = Field(..., min_length=1, description="Promotion description")
    tipo_descuento: TipoDescuento = Field(..., description="Discount type: 'porcentaje' or 'monto_fijo'")
    valor_descuento: Decimal = Field(..., gt=0, description="Discount value")
    fecha_inicio: date = Field(..., description="Start date (YYYY-MM-DD)")
    fecha_fin: date = Field(..., description="End date (YYYY-MM-DD)")
    activo: bool = Field(True, description="Promotion active status")

    @field_validator('titulo')
    @classmethod
    def validate_titulo(cls, v: str) -> str:
        """Validate promotion title is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('El título de la promoción es requerido')
        return v.strip()

    @field_validator('descripcion')
    @classmethod
    def validate_descripcion(cls, v: str) -> str:
        """Validate promotion description is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError('La descripción de la promoción es requerida')
        return v.strip()

    @field_validator('valor_descuento')
    @classmethod
    def validate_valor_descuento(cls, v: Decimal, info) -> Decimal:
        """Validate discount value based on discount type"""
        # Get tipo_descuento from the data being validated
        tipo_descuento = info.data.get('tipo_descuento')

        if tipo_descuento == TipoDescuento.PORCENTAJE:
            # For percentage: must be between 0.01 and 100
            if v < Decimal('0.01') or v > Decimal('100'):
                raise ValueError('El porcentaje debe estar entre 0.01 y 100')
        elif tipo_descuento == TipoDescuento.MONTO_FIJO:
            # For fixed amount: must be positive
            if v <= 0:
                raise ValueError('El monto fijo debe ser mayor a 0')

        # Validate precision (10 total digits, 2 decimal places)
        price_str = str(v)
        digits_only = price_str.replace('.', '').replace('-', '')
        if len(digits_only) > 10:
            raise ValueError('El valor del descuento no puede tener más de 10 dígitos en total')

        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            if len(decimal_part) > 2:
                raise ValueError('El valor del descuento no puede tener más de 2 decimales')

        return v

    @field_validator('fecha_inicio')
    @classmethod
    def validate_fecha_inicio(cls, v: date) -> date:
        """Validate start date is not in the past"""
        from datetime import date as dt_date
        today = dt_date.today()
        if v < today:
            raise ValueError('La fecha de inicio no puede ser anterior a hoy')
        return v

    @field_validator('fecha_fin')
    @classmethod
    def validate_fecha_fin(cls, v: date, info) -> date:
        """Validate end date is greater than or equal to start date"""
        fecha_inicio = info.data.get('fecha_inicio')
        if fecha_inicio and v < fecha_inicio:
            raise ValueError('La fecha fin debe ser mayor o igual a la fecha de inicio')
        return v


class PromocionUpdateRequest(BaseModel):
    """Request body for updating an existing promotion"""
    titulo: Optional[str] = Field(None, min_length=1, max_length=150, description="Promotion title")
    descripcion: Optional[str] = Field(None, min_length=1, description="Promotion description")
    tipo_descuento: Optional[TipoDescuento] = Field(None, description="Discount type")
    valor_descuento: Optional[Decimal] = Field(None, gt=0, description="Discount value")
    fecha_inicio: Optional[date] = Field(None, description="Start date (YYYY-MM-DD)")
    fecha_fin: Optional[date] = Field(None, description="End date (YYYY-MM-DD)")
    activo: Optional[bool] = Field(None, description="Promotion active status")

    @field_validator('titulo')
    @classmethod
    def validate_titulo(cls, v: Optional[str]) -> Optional[str]:
        """Validate promotion title if provided"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError('El título de la promoción no puede estar vacío')
        return v.strip() if v else v

    @field_validator('descripcion')
    @classmethod
    def validate_descripcion(cls, v: Optional[str]) -> Optional[str]:
        """Validate promotion description if provided"""
        if v is not None and len(v.strip()) == 0:
            raise ValueError('La descripción de la promoción no puede estar vacía')
        return v.strip() if v else v

    @field_validator('valor_descuento')
    @classmethod
    def validate_valor_descuento(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        """Validate discount value if provided"""
        if v is None:
            return v

        tipo_descuento = info.data.get('tipo_descuento')

        if tipo_descuento == TipoDescuento.PORCENTAJE:
            if v < Decimal('0.01') or v > Decimal('100'):
                raise ValueError('El porcentaje debe estar entre 0.01 y 100')
        elif tipo_descuento == TipoDescuento.MONTO_FIJO:
            if v <= 0:
                raise ValueError('El monto fijo debe ser mayor a 0')

        # Validate precision
        price_str = str(v)
        digits_only = price_str.replace('.', '').replace('-', '')
        if len(digits_only) > 10:
            raise ValueError('El valor del descuento no puede tener más de 10 dígitos en total')

        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            if len(decimal_part) > 2:
                raise ValueError('El valor del descuento no puede tener más de 2 decimales')

        return v

    @field_validator('fecha_inicio')
    @classmethod
    def validate_fecha_inicio(cls, v: Optional[date]) -> Optional[date]:
        """Validate start date is not in the past if provided"""
        if v is None:
            return v

        from datetime import date as dt_date
        today = dt_date.today()
        if v < today:
            raise ValueError('La fecha de inicio no puede ser anterior a hoy')
        return v

    @field_validator('fecha_fin')
    @classmethod
    def validate_fecha_fin(cls, v: Optional[date], info) -> Optional[date]:
        """Validate end date if provided"""
        if v is None:
            return v

        fecha_inicio = info.data.get('fecha_inicio')
        if fecha_inicio and v < fecha_inicio:
            raise ValueError('La fecha fin debe ser mayor o igual a la fecha de inicio')
        return v


# ===== Response Models =====

class PromocionResponse(BaseModel):
    """Response with promotion details"""
    id: int = Field(..., description="Promotion ID")
    negocio_id: int = Field(..., description="Business ID")
    titulo: str = Field(..., description="Promotion title")
    descripcion: Optional[str] = Field(None, description="Promotion description")
    tipo_descuento: str = Field(..., description="Discount type")
    valor_descuento: Decimal = Field(..., description="Discount value")
    fecha_inicio: date = Field(..., description="Start date")
    fecha_fin: date = Field(..., description="End date")
    activo: bool = Field(..., description="Promotion active status")
    eliminado: bool = Field(..., description="Promotion deleted status")
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
                "titulo": "Descuento de verano",
                "descripcion": "20% en todos los servicios",
                "tipo_descuento": "porcentaje",
                "valor_descuento": 20.00,
                "fecha_inicio": "2025-06-01",
                "fecha_fin": "2025-08-31",
                "activo": True,
                "eliminado": False,
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:00",
                "created_by": 1,
                "updated_by": 1
            }
        }


class PromocionListResponse(BaseModel):
    """Response with list of promotions"""
    promociones: list[PromocionResponse] = Field(..., description="List of promotions")
    total: int = Field(..., description="Total number of promotions")

    class Config:
        json_schema_extra = {
            "example": {
                "promociones": [
                    {
                        "id": 1,
                        "negocio_id": 123,
                        "titulo": "Descuento de verano",
                        "descripcion": "20% en todos los servicios",
                        "tipo_descuento": "porcentaje",
                        "valor_descuento": 20.00,
                        "fecha_inicio": "2025-06-01",
                        "fecha_fin": "2025-08-31",
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


class PromocionSaveResponse(BaseModel):
    """Response after saving/updating a promotion"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: PromocionResponse = Field(..., description="Saved promotion data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Promoción guardada exitosamente",
                "data": {
                    "id": 1,
                    "negocio_id": 123,
                    "titulo": "Descuento de verano",
                    "descripcion": "20% en todos los servicios",
                    "tipo_descuento": "porcentaje",
                    "valor_descuento": 20.00,
                    "fecha_inicio": "2025-06-01",
                    "fecha_fin": "2025-08-31",
                    "activo": True,
                    "eliminado": False,
                    "created_at": "2024-01-15T10:30:00",
                    "updated_at": "2024-01-15T10:30:00",
                    "created_by": 1,
                    "updated_by": 1
                }
            }
        }


class PromocionDeleteResponse(BaseModel):
    """Response after deleting a promotion"""
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Promoción eliminada exitosamente"
            }
        }
