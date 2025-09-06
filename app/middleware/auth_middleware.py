# ==========================================
# app/middleware/auth_middleware.py - Middleware de autenticación
# ==========================================

"""Middleware para extraer tokens de cookies y simular header Authorization"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import MutableMapping
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware para extraer access token de cookies HttpOnly
    y simular header Authorization para compatibilidad con HTTPBearer
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Procesar request y extraer token de cookie
        
        Flujo:
        1. Verificar si hay access_token en cookies
        2. Si no hay header Authorization, simularlo
        3. Continuar con el request normal
        """
        
        try:
            # Extraer access token de cookie HttpOnly
            access_token = request.cookies.get("access_token")
            
            # Si hay token en cookie y NO hay header Authorization
            if access_token and not request.headers.get("authorization"):
                
                # Crear headers mutables para modificar
                mutable_headers = dict(request.headers)
                mutable_headers["authorization"] = f"Bearer {access_token}"
                
                # Actualizar headers en el request
                # Método 1: Actualizar scope directamente
                header_list = []
                for key, value in mutable_headers.items():
                    header_list.append((key.encode().lower(), value.encode()))
                
                request.scope["headers"] = header_list
                
                logger.debug("Access token extracted from cookie and added to Authorization header")
            
            # Continuar con el procesamiento normal
            response = await call_next(request)
            return response
            
        except Exception as e:
            logger.error(f"Error in auth middleware: {e}")
            # En caso de error, continuar sin modificar headers
            return await call_next(request)