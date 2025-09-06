# ==========================================
# app/middleware/logging.py - Middleware de logging
# ==========================================

"""Middleware de logging para requests HTTP"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
import json
from datetime import datetime

# Logger específico para este middleware
logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para logging completo de requests HTTP
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Rutas a excluir del logging detallado (health checks, etc.)
        self.exclude_paths = [
            "/health",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/favicon.ico"
        ]
        
        # Log de inicialización
        logger.info("🔧 LoggingMiddleware inicializado")
    
    async def dispatch(self, request: Request, call_next):
        """Loggear request y response con timing"""
        
        start_time = time.time()
        request_id = id(request)  # ID único para el request
        
        # Información básica del request
        method = request.method
        path = request.url.path
        query_string = str(request.query_params) if request.query_params else ""
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Log de entrada (solo para rutas importantes)
        if path not in self.exclude_paths:
            logger.info(f"🔥 [{request_id}] {method} {path} - IP: {client_ip}")
        
        response = None
        error_occurred = False
        
        try:
            # Procesar request
            response = await call_next(request)
            
        except Exception as e:
            error_occurred = True
            logger.error(f"💥 [{request_id}] Exception: {type(e).__name__}: {str(e)}")
            raise  # Re-lanzar para que FastAPI lo maneje
        
        finally:
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_time
            
            # Preparar datos de log
            log_data = {
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "method": method,
                "path": path,
                "query_string": query_string,
                "status_code": response.status_code if response else 500,
                "process_time_seconds": round(process_time, 3),
                "client_ip": client_ip,
                "user_agent": user_agent[:200] if user_agent else "",
                "content_length": response.headers.get("content-length", "unknown") if response else "unknown",
                "error": error_occurred
            }
            
            # Logging diferenciado por severidad
            self._log_request_response(log_data, path)
            
            # Agregar headers de timing al response
            if response:
                response.headers["X-Process-Time"] = str(round(process_time, 3))
                response.headers["X-Request-ID"] = str(request_id)
                response.headers["X-Timestamp"] = datetime.utcnow().isoformat()
        
        return response
    
    def _log_request_response(self, log_data: dict, path: str):
        """Logging diferenciado por nivel de severidad"""
        
        status_code = log_data.get("status_code", 0)
        process_time = log_data.get("process_time_seconds", 0)
        method = log_data.get("method")
        client_ip = log_data.get("client_ip")
        request_id = log_data.get("request_id")
        error_occurred = log_data.get("error", False)
        
        # Mensaje base
        base_msg = f"[{request_id}] {method} {path} - {status_code} - {process_time:.3f}s - {client_ip}"
        
        # Logging diferenciado por status code
        if error_occurred:
            # Errores de aplicación (excepciones)
            logger.error(f"💥 {base_msg} - EXCEPTION")
            logger.error(f"💥 [{request_id}] Full details: {json.dumps(log_data, indent=2)}")
        
        elif status_code >= 500:
            # Errores de servidor
            logger.error(f"🚨 {base_msg} - SERVER_ERROR")
            logger.error(f"🚨 [{request_id}] Details: {json.dumps(log_data)}")
        
        elif status_code >= 400:
            # Errores de cliente
            if path not in self.exclude_paths:
                logger.warning(f"⚠️  {base_msg} - CLIENT_ERROR")
        
        elif status_code >= 300:
            # Redirects
            if path not in self.exclude_paths:
                logger.info(f"↩️  {base_msg} - REDIRECT")
        
        else:
            # Requests exitosos
            if path not in self.exclude_paths:
                logger.info(f"✅ {base_msg} - SUCCESS")
        
        # Log especial para requests lentos
        if process_time > 2.0:  # Más de 2 segundos
            logger.warning(f"🐌 {base_msg} - SLOW_REQUEST (threshold: 2.0s)")
            
        # Log especial para requests muy lentos
        if process_time > 5.0:  # Más de 5 segundos
            logger.error(f"🐌 {base_msg} - VERY_SLOW_REQUEST")
            logger.error(f"🐌 [{request_id}] Slow request details: {json.dumps(log_data)}")
    
    def _get_client_ip(self, request: Request) -> str:
        """Obtener IP real del cliente considerando proxies"""
        
        # Headers comunes de proxies y load balancers
        headers_to_check = [
            "x-forwarded-for",
            "x-real-ip",
            "cf-connecting-ip",  # Cloudflare
            "x-forwarded",
            "forwarded-for",
            "forwarded"
        ]
        
        for header in headers_to_check:
            ip = request.headers.get(header)
            if ip:
                # X-Forwarded-For puede contener múltiples IPs
                if "," in ip:
                    ip = ip.split(",")[0].strip()
                
                # Validar que no esté vacío
                if ip and ip.lower() != "unknown":
                    return ip
        
        # Fallback a la IP directa
        return getattr(request.client, 'host', 'unknown')