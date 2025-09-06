"""Funciones de seguridad: JWT, bcrypt, tokens"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import jwt
import bcrypt
import hashlib
import secrets
from app.config import settings

def hash_password(password: str) -> str:
    """Hashear password con bcrypt"""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verificar password"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(data: Dict[str, Any]) -> str:
    """Crear access token JWT"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: Dict[str, Any]) -> str:
    """Crear refresh token JWT"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def verify_token(token: str) -> Dict[str, Any]:
    """Verificar y decodificar token JWT"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

def generate_session_id() -> str:
    """Generar ID único de sesión"""
    return hashlib.md5(f"{datetime.utcnow()}{secrets.token_hex(16)}".encode()).hexdigest()

def generate_jti() -> str:
    """Generar JTI único para tokens"""
    return hashlib.md5(f"{datetime.utcnow()}{secrets.token_hex(8)}".encode()).hexdigest()

def generate_csrf_token() -> str:
    """Generar token CSRF seguro"""
    return secrets.token_urlsafe(32)

def verify_csrf_token(token: str, stored_token: str) -> bool:
    """Verificar token CSRF"""
    if not token or not stored_token:
        return False
    return secrets.compare_digest(token, stored_token)

def generate_reset_token() -> str:
    """Generar token para reset de contraseña"""
    return secrets.token_urlsafe(32)

def generate_verification_token() -> str:
    """Generar token para verificación de email"""
    return secrets.token_urlsafe(32)