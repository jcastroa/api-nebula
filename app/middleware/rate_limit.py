# ==========================================
# app/middleware/rate_limit.py - Middleware de rate limiting
# ==========================================

"""Middleware de rate limiting por IP para endpoints sensibles"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.redis_client import redis_client
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware para rate limiting por IP en endpoints sensibles
    """
    
    def __init__(self, app, requests_per_window: int = None, window_seconds: int = None):
        super().__init__(app)
        self.requests_per_window = requests_per_window or settings.RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW
        
        # Endpoints que requieren rate limiting
        self.sensitive_endpoints = [
            "/api/v1/auth/login",
            "/api/v1/auth/refresh", 
            "/api/v1/users/change-password"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Aplicar rate limiting a endpoints sensibles"""
        
        # Solo aplicar rate limiting a endpoints sensibles
        if request.url.path in self.sensitive_endpoints:
            client_ip = self._get_client_ip(request)
            
            # Verificar rate limit
            if not await self._check_rate_limit(client_ip, request.url.path):
                logger.warning(
                    f"Rate limit exceeded for IP {client_ip} on endpoint {request.url.path}"
                )
                
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "detail": f"Rate limit exceeded. Max {self.requests_per_window} requests per {self.window_seconds} seconds.",
                        "retry_after": self.window_seconds
                    },
                    headers={"Retry-After": str(self.window_seconds)}
                )
        
        # Continuar con procesamiento normal
        response = await call_next(request)
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Obtener IP real del cliente considerando proxies
        
        Orden de prioridad:
        1. X-Forwarded-For (primer IP)
        2. X-Real-IP
        3. CF-Connecting-IP (Cloudflare)  
        4. IP directa del cliente
        """
        # X-Forwarded-For puede contener múltiples IPs
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Tomar la primera IP (cliente original)
            return forwarded_for.split(",")[0].strip()
        
        # X-Real-IP (usado por algunos proxies)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        
        # Cloudflare
        cf_connecting_ip = request.headers.get("cf-connecting-ip")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        # Fallback a IP directa
        return request.client.host
    
    async def _check_rate_limit(self, client_ip: str, endpoint: str) -> bool:
        """
        Verificar rate limit para IP y endpoint específico
        
        Args:
            client_ip: IP del cliente
            endpoint: Endpoint solicitado
            
        Returns:
            True si está dentro del límite
        """
        try:
            # Crear clave específica para IP + endpoint
            key = f"rate_limit:{endpoint.replace('/', '_')}:{client_ip}"
            
            # Incrementar contador con TTL
            current_requests = redis_client.increment(key, ttl=self.window_seconds)
            
            # Verificar límite
            if current_requests > self.requests_per_window:
                return False
            
            # Log para debugging (solo primeras requests)
            if current_requests <= 2:
                logger.debug(f"Rate limit check: {client_ip} -> {endpoint} ({current_requests}/{self.requests_per_window})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # En caso de error de Redis, permitir request (fail open)
            return True
    
    async def get_rate_limit_status(self, client_ip: str, endpoint: str) -> dict:
        """
        Obtener status actual del rate limit para una IP/endpoint
        
        Útil para endpoints de diagnóstico
        """
        try:
            key = f"rate_limit:{endpoint.replace('/', '_')}:{client_ip}"
            current = redis_client.get_json(key) or 0
            
            return {
                "ip": client_ip,
                "endpoint": endpoint,
                "current_requests": int(current),
                "limit": self.requests_per_window,
                "window_seconds": self.window_seconds,
                "remaining": max(0, self.requests_per_window - int(current))
            }
        except Exception as e:
            logger.error(f"Error getting rate limit status: {e}")
            return {"error": str(e)}