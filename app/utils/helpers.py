# ==========================================
# app/utils/helpers.py - Funciones auxiliares generales
# ==========================================

"""Funciones auxiliares y utilidades generales"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import re
import secrets
import string
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

# ==========================================
# UTILIDADES DE FECHAS Y TIEMPO
# ==========================================

def get_utc_now() -> datetime:
    """Obtener timestamp UTC actual"""
    return datetime.now(timezone.utc)

def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Formatear datetime a string legible"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime(format_str)

def parse_datetime_string(date_str: str) -> Optional[datetime]:
    """Parsear string de fecha a datetime"""
    try:
        # Intentar formato ISO
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Intentar otros formatos comunes
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date string: {date_str}")
    return None

def time_ago_string(dt: datetime) -> str:
    """Convertir datetime a string 'tiempo atrás'"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = get_utc_now()
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return f"{int(seconds)} segundos atrás"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minuto{'s' if minutes != 1 else ''} atrás"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hora{'s' if hours != 1 else ''} atrás"
    elif seconds < 2592000:  # 30 días
        days = int(seconds / 86400)
        return f"{days} día{'s' if days != 1 else ''} atrás"
    else:
        return format_datetime(dt, "%d/%m/%Y")

def is_recent(dt: datetime, minutes: int = 5) -> bool:
    """Verificar si un datetime es reciente (últimos N minutos)"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = get_utc_now()
    return (now - dt).total_seconds() < (minutes * 60)

# ==========================================
# UTILIDADES DE STRINGS
# ==========================================

def generate_random_string(length: int = 16, include_numbers: bool = True, include_symbols: bool = False) -> str:
    """Generar string aleatorio seguro"""
    characters = string.ascii_letters
    
    if include_numbers:
        characters += string.digits
    
    if include_symbols:
        characters += "!@#$%^&*"
    
    return ''.join(secrets.choice(characters) for _ in range(length))

def generate_code(length: int = 6, numbers_only: bool = True) -> str:
    """Generar código numérico o alfanumérico"""
    if numbers_only:
        return ''.join(secrets.choice(string.digits) for _ in range(length))
    else:
        # Códigos alfanuméricos sin caracteres confusos
        characters = "ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"  # Sin O, 0
        return ''.join(secrets.choice(characters) for _ in range(length))

def sanitize_string(text: str, max_length: int = None) -> str:
    """Limpiar y sanitizar string de input"""
    if not text:
        return ""
    
    # Remover caracteres de control y espacios extras
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(text))
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Limitar longitud si se especifica
    if max_length:
        cleaned = cleaned[:max_length]
    
    return cleaned

def slugify(text: str) -> str:
    """Convertir texto a slug URL-friendly"""
    # Convertir a minúsculas y remover acentos básicos
    text = text.lower()
    text = re.sub(r'[áàäâ]', 'a', text)
    text = re.sub(r'[éèëê]', 'e', text)
    text = re.sub(r'[íìïî]', 'i', text)
    text = re.sub(r'[óòöô]', 'o', text)
    text = re.sub(r'[úùüû]', 'u', text)
    text = re.sub(r'[ñ]', 'n', text)
    
    # Remover caracteres especiales y espacios
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    
    return text.strip('-')

def mask_email(email: str) -> str:
    """Enmascarar email para logs (user@domain.com -> u***@domain.com)"""
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return email
    
    masked_local = local[0] + '*' * (len(local) - 1)
    return f"{masked_local}@{domain}"

def mask_ip(ip: str) -> str:
    """Enmascarar IP para privacidad (192.168.1.100 -> 192.168.1.xxx)"""
    if not ip:
        return ip
    
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    
    # Para IPv6 o formatos no estándar
    if ':' in ip:
        parts = ip.split(':')
        if len(parts) >= 4:
            return ':'.join(parts[:4]) + ':xxxx'
    
    return ip

# ==========================================
# UTILIDADES DE VALIDACIÓN
# ==========================================

def validate_email(email: str) -> bool:
    """Validar formato de email básico"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_username(username: str) -> Dict[str, Any]:
    """Validar username con reglas específicas"""
    result = {
        "valid": True,
        "errors": []
    }
    
    if not username:
        result["valid"] = False
        result["errors"].append("Username is required")
        return result
    
    if len(username) < 3:
        result["valid"] = False
        result["errors"].append("Username must be at least 3 characters")
    
    if len(username) > 50:
        result["valid"] = False
        result["errors"].append("Username must be less than 50 characters")
    
    # Solo letras, números, guiones y guiones bajos
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        result["valid"] = False
        result["errors"].append("Username can only contain letters, numbers, hyphens and underscores")
    
    # No puede empezar o terminar con guiones
    if username.startswith('-') or username.endswith('-'):
        result["valid"] = False
        result["errors"].append("Username cannot start or end with hyphens")
    
    return result

def validate_password_strength(password: str) -> Dict[str, Any]:
    """Validar fortaleza de password"""
    result = {
        "valid": True,
        "score": 0,
        "errors": [],
        "suggestions": []
    }
    
    if not password:
        result["valid"] = False
        result["errors"].append("Password is required")
        return result
    
    # Longitud mínima
    if len(password) < 8:
        result["valid"] = False
        result["errors"].append("Password must be at least 8 characters")
    else:
        result["score"] += 1
    
    # Verificar complejidad
    has_lower = bool(re.search(r'[a-z]', password))
    has_upper = bool(re.search(r'[A-Z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_symbol = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'"\\|,.<>?]', password))
    
    if has_lower:
        result["score"] += 1
    else:
        result["suggestions"].append("Add lowercase letters")
    
    if has_upper:
        result["score"] += 1
    else:
        result["suggestions"].append("Add uppercase letters")
    
    if has_digit:
        result["score"] += 1
    else:
        result["suggestions"].append("Add numbers")
    
    if has_symbol:
        result["score"] += 1
    else:
        result["suggestions"].append("Add special characters")
    
    # Longitud adicional
    if len(password) >= 12:
        result["score"] += 1
    
    # Patrones comunes débiles
    weak_patterns = [
        r'123456', r'password', r'qwerty', r'admin',
        r'(.)\1{3,}',  # Caracteres repetidos
        r'1234', r'abcd'
    ]
    
    for pattern in weak_patterns:
        if re.search(pattern, password.lower()):
            result["score"] -= 1
            result["suggestions"].append("Avoid common patterns")
            break
    
    # Evaluar score final
    if result["score"] < 3 and result["valid"]:
        result["suggestions"].append("Consider using a longer, more complex password")
    
    return result

def validate_ip_address(ip: str) -> bool:
    """Validar formato de dirección IP"""
    # IPv4
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ipv4_pattern, ip):
        parts = ip.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    
    # IPv6 básico
    if ':' in ip:
        return bool(re.match(r'^([0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}$', ip))
    
    return False

# ==========================================
# UTILIDADES DE DATOS
# ==========================================

def safe_dict_get(data: dict, key: str, default: Any = None) -> Any:
    """Obtener valor de diccionario de forma segura"""
    try:
        return data.get(key, default)
    except (AttributeError, TypeError):
        return default

def merge_dicts(*dicts: dict) -> dict:
    """Combinar múltiples diccionarios"""
    result = {}
    for d in dicts:
        if isinstance(d, dict):
            result.update(d)
    return result

def filter_dict_keys(data: dict, allowed_keys: List[str]) -> dict:
    """Filtrar diccionario solo con claves permitidas"""
    return {k: v for k, v in data.items() if k in allowed_keys}

def remove_none_values(data: dict) -> dict:
    """Remover valores None de un diccionario"""
    return {k: v for k, v in data.items() if v is not None}

def flatten_dict(data: dict, separator: str = '.') -> dict:
    """Aplanar diccionario anidado"""
    def _flatten(obj, parent_key=''):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{parent_key}{separator}{k}" if parent_key else k
                items.extend(_flatten(v, new_key).items())
        else:
            return {parent_key: obj}
        return dict(items)
    
    return _flatten(data)

# ==========================================
# UTILIDADES DE HASH Y ENCODING
# ==========================================

def generate_hash(data: str, algorithm: str = 'sha256') -> str:
    """Generar hash de string"""
    algorithms = {
        'md5': hashlib.md5,
        'sha1': hashlib.sha1,
        'sha256': hashlib.sha256,
        'sha512': hashlib.sha512
    }
    
    if algorithm not in algorithms:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    hash_func = algorithms[algorithm]()
    hash_func.update(data.encode('utf-8'))
    return hash_func.hexdigest()

def generate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """Generar hash de archivo"""
    algorithms = {
        'md5': hashlib.md5,
        'sha256': hashlib.sha256,
        'sha512': hashlib.sha512
    }
    
    if algorithm not in algorithms:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    hash_func = algorithms[algorithm]()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()

# ==========================================
# UTILIDADES DE JSON
# ==========================================

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Parse JSON de forma segura"""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dumps(data: Any, indent: int = None) -> str:
    """Serializar a JSON de forma segura"""
    try:
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger.error(f"Error serializing to JSON: {e}")
        return "{}"

def clean_json_for_logging(data: dict, sensitive_keys: List[str] = None) -> dict:
    """Limpiar datos JSON para logging (remover información sensible)"""
    if sensitive_keys is None:
        sensitive_keys = [
            'password', 'token', 'secret', 'key', 'authorization',
            'cookie', 'session', 'csrf', 'api_key'
        ]
    
    cleaned = {}
    for k, v in data.items():
        key_lower = k.lower()
        
        # Verificar si la clave contiene información sensible
        is_sensitive = any(sensitive_key in key_lower for sensitive_key in sensitive_keys)
        
        if is_sensitive:
            if isinstance(v, str) and len(v) > 8:
                # Mostrar solo primeros y últimos caracteres
                cleaned[k] = f"{v[:4]}***{v[-4:]}"
            else:
                cleaned[k] = "***HIDDEN***"
        elif isinstance(v, dict):
            # Recursivamente limpiar diccionarios anidados
            cleaned[k] = clean_json_for_logging(v, sensitive_keys)
        else:
            cleaned[k] = v
    
    return cleaned