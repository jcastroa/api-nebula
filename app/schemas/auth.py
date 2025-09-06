# ==========================================
# app/schemas/auth.py - Schemas de autenticación
# ==========================================

"""Schemas Pydantic para endpoints de autenticación"""
from pydantic import BaseModel, validator
from typing import Dict, Any, Optional, List
from datetime import datetime

class LoginRequest(BaseModel):
    """Request para login"""
    username: str
    password: str
    recaptcha_token: str
    device_info: Optional[Dict[str, Any]] = {}
    
    @validator('username')
    def username_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v.strip().lower()
    
    @validator('password')
    def password_must_have_minimum_length(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        return v

class UsuarioInfo(BaseModel):
    """Información básica del usuario"""
    id: int
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool

class RolInfo(BaseModel):
    """Información de un rol"""
    id: int
    nombre: str
    descripcion: Optional[str] = None

class ConsultorioInfo(BaseModel):
    """Información básica de un consultorio"""
    id: int
    nombre: str

class ConsultorioDetallado(BaseModel):
    """Información detallada de consultorio con rol del usuario"""
    consultorio_id: int
    nombre: str
    ruc: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    estado: str
    rol_id: int
    rol_nombre: str
    rol_descripcion: Optional[str] = None
    es_principal: bool
    estado_asignacion: str
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None

class ConsultorioSimple(BaseModel):
    """Consultorio simple para superadmin"""
    consultorio_id: int
    nombre: str
    ruc: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    estado: str
    es_principal: bool

class AccionInfo(BaseModel):
    """Información de una acción"""
    accion_id: int
    nombre: str
    descripcion: Optional[str] = None
    codigo: str

class ModuloInfo(BaseModel):
    """Información de un módulo del menú"""
    modulo_id: int
    nombre: str
    descripcion: Optional[str] = None
    ruta: Optional[str] = None
    icono: Optional[str] = None
    orden: int
    modulo_padre_id: Optional[int] = None
    acciones: Optional[List[AccionInfo]] = []

class UserCompleteInfo(BaseModel):
    """Información completa del usuario con contexto"""
    usuario: UsuarioInfo
    rol_global: Optional[RolInfo] = None
    consultorio_principal: Optional[ConsultorioInfo] = None
    ultimo_consultorio_activo: Optional[ConsultorioInfo] = None
    consultorio_contexto_actual: Optional[int] = None
    consultorios_usuario: List[ConsultorioDetallado] = []
    todos_consultorios: Optional[List[ConsultorioSimple]] = None
    menu_modulos: List[ModuloInfo] = []
    permisos_lista: List[str] = []
    rol_activo: Optional[int] = None
    es_superadmin: bool = False


class TokenResponse(BaseModel):
    """Response de login exitoso"""
    message: str
    user: UserCompleteInfo
    expires_in: int
    session_id: str
    csrf_token: Optional[str] = None

class RefreshResponse(BaseModel):
    """Response de refresh exitoso"""
    message: str
    expires_in: int
    csrf_token: Optional[str] = None

class LogoutResponse(BaseModel):
    """Response de logout"""
    message: str
    logged_out_at: datetime

class SessionInfo(BaseModel):
    """Información de sesión para admin"""
    id: int
    session_id: str
    user_id: int
    username: str
    ip_address: str
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    created_at: datetime
    last_activity: datetime
    status: str
    expires_at: datetime

class CambiarConsultorioRequest(BaseModel):
    consultorio_id: int