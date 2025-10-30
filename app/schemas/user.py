# ==========================================
# app/schemas/user.py - Schemas de usuario
# ==========================================

"""Schemas Pydantic para gestión de usuarios"""
from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional
from datetime import datetime

class UserCreate(BaseModel):
    """Schema para crear usuario"""
    username: str
    email: EmailStr
    password: Optional[str] = None
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    rol_global_id: Optional[int] = None

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, - and _')
        return v.lower().strip()

    @validator('password')
    def validate_password(cls, v):
        if v and len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @validator('nombres', 'apellidos')
    def validate_names(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip().title() if v else None

class UserUpdate(BaseModel):
    """Schema para actualizar usuario"""
    email: Optional[EmailStr] = None
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    is_active: Optional[bool] = None
    rol_global_id: Optional[int] = None
    
    @validator('nombres', 'apellidos')
    def validate_names(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip().title() if v else None

class UserResponse(BaseModel):
    """Schema para respuesta de usuario"""
    id: int
    username: str
    email: str
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    is_active: bool = True
    rol_global_id: Optional[int] = None
    rol_global_nombre: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    asignaciones: Optional[List[dict]] = []
    
    class Config:
        from_attributes = True

class PasswordChangeRequest(BaseModel):
    """Schema para cambio de contraseña"""
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('New password must be at least 8 characters')
        return v

class UserListResponse(BaseModel):
    """Schema para lista paginada de usuarios"""
    users: list[UserResponse]
    total: int
    page: int
    size: int

# ==========================================
# Schemas para asignaciones de usuarios a negocios
# ==========================================

class AssignmentCreate(BaseModel):
    """Schema para crear asignación de usuario a negocio"""
    usuario_id: int
    negocio_id: int
    rol_id: int
    es_principal: bool = False
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None

    @validator('usuario_id', 'negocio_id', 'rol_id')
    def validate_ids(cls, v):
        if v <= 0:
            raise ValueError('ID debe ser mayor a 0')
        return v

class AssignmentUpdate(BaseModel):
    """Schema para actualizar asignación"""
    rol_id: Optional[int] = None
    es_principal: Optional[bool] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None

    @validator('rol_id')
    def validate_rol_id(cls, v):
        if v is not None and v <= 0:
            raise ValueError('rol_id debe ser mayor a 0')
        return v

class AssignmentResponse(BaseModel):
    """Schema para respuesta de asignación"""
    id: int
    usuario_id: int
    consultorio_id: int
    consultorio_nombre: Optional[str] = None
    rol_id: int
    rol_nombre: Optional[str] = None
    es_principal: bool
    estado: str
    fecha_asignacion: datetime
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RoleResponse(BaseModel):
    """Schema para respuesta de rol"""
    id_rol: int
    nombre: str
    descripcion: Optional[str] = None
    activo: Optional[bool] = True
    fecha_creacion: Optional[datetime] = None

    class Config:
        from_attributes = True