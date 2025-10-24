# app/schemas/negocio.py
"""
Schemas de validación para negocios
"""
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime


class NegocioBase(BaseModel):
    """Schema base para negocio"""
    nombre: str
    ruc: Optional[str] = None
    telefono_contacto: Optional[str] = None
    email: Optional[EmailStr] = None
    nombre_responsable: Optional[str] = None
    direccion: Optional[str] = None
    activo: bool = True
    permite_pago: bool = False
    envia_recordatorios: bool = False
    es_principal: bool = False
    con_confirmacion_cita: bool = False

    @validator('nombre')
    def validate_nombre(cls, v):
        """Validar que el nombre no esté vacío"""
        if not v or not v.strip():
            raise ValueError('El nombre del negocio es requerido')
        return v.strip()

    @validator('ruc')
    def validate_ruc(cls, v):
        """Validar formato de RUC si se proporciona"""
        if v:
            v = v.strip()
            # Validar que contenga solo números y tenga longitud válida (11 dígitos para Perú)
            if not v.isdigit():
                raise ValueError('El RUC debe contener solo números')
            if len(v) != 11:
                raise ValueError('El RUC debe tener 11 dígitos')
        return v

    @validator('telefono_contacto')
    def validate_telefono(cls, v):
        """Validar formato de teléfono si se proporciona"""
        if v:
            v = v.strip()
            # Remover caracteres comunes en teléfonos
            cleaned = v.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not cleaned.isdigit():
                raise ValueError('El teléfono debe contener solo números')
        return v


class NegocioCreate(NegocioBase):
    """Schema para crear un negocio"""
    pass


class NegocioUpdate(BaseModel):
    """Schema para actualizar un negocio (todos los campos opcionales)"""
    nombre: Optional[str] = None
    ruc: Optional[str] = None
    telefono_contacto: Optional[str] = None
    email: Optional[EmailStr] = None
    nombre_responsable: Optional[str] = None
    direccion: Optional[str] = None
    activo: Optional[bool] = None
    permite_pago: Optional[bool] = None
    envia_recordatorios: Optional[bool] = None
    es_principal: Optional[bool] = None
    con_confirmacion_cita: Optional[bool] = None

    @validator('nombre')
    def validate_nombre(cls, v):
        """Validar que el nombre no esté vacío si se proporciona"""
        if v is not None and (not v or not v.strip()):
            raise ValueError('El nombre del negocio no puede estar vacío')
        return v.strip() if v else v

    @validator('ruc')
    def validate_ruc(cls, v):
        """Validar formato de RUC si se proporciona"""
        if v:
            v = v.strip()
            if not v.isdigit():
                raise ValueError('El RUC debe contener solo números')
            if len(v) != 11:
                raise ValueError('El RUC debe tener 11 dígitos')
        return v

    @validator('telefono_contacto')
    def validate_telefono(cls, v):
        """Validar formato de teléfono si se proporciona"""
        if v:
            v = v.strip()
            cleaned = v.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not cleaned.isdigit():
                raise ValueError('El teléfono debe contener solo números')
        return v


class NegocioEstadoUpdate(BaseModel):
    """Schema para actualizar el estado de un negocio"""
    activo: bool


class NegocioResponse(NegocioBase):
    """Schema para respuesta de negocio"""
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    estado: Optional[str] = None
    existe_en_firestore: Optional[bool] = False

    class Config:
        from_attributes = True


class NegocioListResponse(BaseModel):
    """Schema para lista de negocios"""
    success: bool
    total: int
    data: list[NegocioResponse]
    message: str
