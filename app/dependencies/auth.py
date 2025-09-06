from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from typing import Optional
import hashlib
from ..core.database import get_db_connection

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_api_key_hash(api_key: str) -> str:
    """Genera el hash de la API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()

async def validate_api_key(
    api_key: Optional[str] = Security(API_KEY_HEADER)
) -> str:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API Key no proporcionada"
        )
    
    api_key_hash = get_api_key_hash(api_key)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_api_key, nombre_aplicacion, activo 
            FROM API_KEYS 
            WHERE api_key_hash = ? AND activo = 1
        """, (api_key_hash,))
        
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(
                status_code=401,
                detail="API Key inválida"
            )
        
        return result.nombre_aplicacion