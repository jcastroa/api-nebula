# ==========================================
# app/utils/__init__.py
# ==========================================

"""
Módulo de utilidades para el sistema de autenticación

Exporta las funciones más comúnmente utilizadas
"""

from .helpers import (
    get_utc_now,
    format_datetime,
    time_ago_string,
    generate_random_string,
    generate_code,
    sanitize_string,
    validate_email,
    validate_username,
    validate_password_strength,
    mask_email,
    mask_ip,
    safe_json_loads,
    safe_json_dumps,
    clean_json_for_logging
)

from .constants import (
    UserStatus,
    SessionStatus,
    TokenType,
    ErrorMessages,
    SuccessMessages,
    AppLimits,
    CacheConfig
)

# Funciones principales exportadas
__all__ = [
    # Utilidades de tiempo
    'get_utc_now',
    'format_datetime', 
    'time_ago_string',
    
    # Utilidades de strings
    'generate_random_string',
    'generate_code',
    'sanitize_string',
    'mask_email',
    'mask_ip',
    
    # Validaciones
    'validate_email',
    'validate_username',
    'validate_password_strength',
    
    # JSON
    'safe_json_loads',
    'safe_json_dumps',
    'clean_json_for_logging',
    
    # Constantes
    'UserStatus',
    'SessionStatus', 
    'TokenType',
    'ErrorMessages',
    'SuccessMessages',
    'AppLimits',
    'CacheConfig'
]