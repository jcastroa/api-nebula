"""Utilidades para convertir dicts a schemas de Pydantic"""
from typing import Dict, Any
import logging
from app.schemas.auth import UserCompleteInfo, UsuarioInfo, RolInfo, ConsultorioInfo, ConsultorioDetallado, ConsultorioSimple, ModuloInfo

logger = logging.getLogger(__name__)

def dict_to_user_complete_info(user_data: Dict[str, Any]) -> UserCompleteInfo:
    """
    Convierte el diccionario de user_data del CRUD a UserCompleteInfo schema
    
    Args:
        user_data: Dict con datos completos del usuario desde el CRUD
        
    Returns:
        UserCompleteInfo: Schema validado de Pydantic
    """
    try:
        return UserCompleteInfo(
            # Datos básicos del usuario
            usuario=UsuarioInfo(**user_data["usuario"]),
            
            # Rol global (puede ser None)
            rol_global=RolInfo(**user_data["rol_global"]) if user_data.get("rol_global") else None,
            
            # Consultorio principal (puede ser None)
            consultorio_principal=ConsultorioInfo(**user_data["consultorio_principal"]) if user_data.get("consultorio_principal") else None,
            
            # Último consultorio activo (puede ser None)
            ultimo_consultorio_activo=ConsultorioInfo(**user_data["ultimo_consultorio_activo"]) if user_data.get("ultimo_consultorio_activo") else None,
            
            # Consultorio contexto actual
            consultorio_contexto_actual=user_data.get("consultorio_contexto_actual"),
            
            # Lista de consultorios del usuario con roles
            consultorios_usuario=[
                ConsultorioDetallado(**consultorio) 
                for consultorio in user_data.get("consultorios_usuario", [])
            ],
            
            # Todos los consultorios (solo para superadmin)
            todos_consultorios=[
                ConsultorioSimple(**consultorio) 
                for consultorio in user_data.get("todos_consultorios", [])
            ] if user_data.get("todos_consultorios") else None,
            
            # Módulos del menú
            menu_modulos=[
                ModuloInfo(**modulo) 
                for modulo in user_data.get("menu_modulos", [])
            ],
            
            # Lista de permisos como strings
            permisos_lista=user_data.get("permisos_lista", []),
            
            # Roles activos del usuario
            rol_activo=user_data.get("rol_activo"),
            
            # Flag de superadmin
            es_superadmin=user_data.get("es_superadmin", False)
        )
        
    except Exception as e:
        logger.error(f"Error converting dict to UserCompleteInfo: {e}")
        logger.error(f"Data received: {user_data}")
        raise ValueError(f"Error converting user data to schema: {e}")

