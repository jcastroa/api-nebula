"""
Punto de entrada principal de la aplicación FastAPI
"""
import os
import logging

# ==========================================
# INICIALIZAR LOGGING ANTES QUE TODO
# ==========================================
from app.core.logging import setup_logging

# Configurar logging al inicio
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"

setup_logging(log_level=LOG_LEVEL, log_to_file=LOG_TO_FILE)

# ==========================================
# AHORA IMPORTAR EL RESTO
# ==========================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import api_router
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.logging import LoggingMiddleware
from app.workers.scheduler import start_background_tasks

# Logger para este módulo
logger = logging.getLogger(__name__)

def create_application() -> FastAPI:
    """Crear y configurar aplicación FastAPI"""
    
    logger.info("🏗️  Creando aplicación FastAPI...")
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )
    
    logger.info("🔧 Configurando middlewares...")
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Middlewares customizados (orden importa)
    # LoggingMiddleware debe ir PRIMERO para capturar todo
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    
    logger.info("📚 Registrando routers...")
    
    # Routers
    app.include_router(api_router, prefix="/api/v1")
    
    # Eventos
    app.add_event_handler("startup", startup_handler)
    app.add_event_handler("shutdown", shutdown_handler)
    
    logger.info("✅ Aplicación FastAPI creada correctamente")
    
    return app

async def startup_handler():
    """Inicialización al arrancar"""
    logger.info("🚀 Iniciando aplicación...")
    logger.info(f"📋 Configuración:")
    logger.info(f"   • Nombre: {settings.APP_NAME}")
    logger.info(f"   • Versión: {settings.APP_VERSION}")
    logger.info(f"   • Debug: {settings.DEBUG}")
    logger.info(f"   • Environment: {settings.ENVIRONMENT}")
    
    try:
        await start_background_tasks()
        logger.info("🔄 Background tasks iniciadas")
    except Exception as e:
        logger.error(f"❌ Error iniciando background tasks: {e}")
        raise
    
    logger.info("✅ Aplicación iniciada correctamente")

async def shutdown_handler():
    """Limpieza al cerrar"""
    logger.info("🛑 Cerrando aplicación...")
    logger.info("✅ Aplicación cerrada correctamente")

# Crear instancia de la aplicación
logger.info("🎯 Inicializando aplicación principal...")
app = create_application()

# Health check básico
@app.get("/")
async def root():
    logger.debug("📍 Root endpoint accessed")
    return {
        "message": "Sistema de Autenticación API", 
        "version": settings.APP_VERSION,
        "status": "running"
    }

# Endpoint para probar logging
@app.get("/test-logging")
async def test_logging():
    """Endpoint para probar que el logging funciona"""
    
    # Probar diferentes niveles
    logger.debug("🐛 DEBUG: Mensaje de debug")
    logger.info("ℹ️  INFO: Endpoint de test ejecutado")
    logger.warning("⚠️  WARNING: Mensaje de advertencia de prueba")
    logger.error("❌ ERROR: Mensaje de error de prueba (simulado)")
    
    # Probar logger específico de middleware
    middleware_logger = logging.getLogger("app.middleware.logging")
    middleware_logger.info("🌐 MIDDLEWARE: Test desde endpoint")
    
    # Probar logger específico de auth
    auth_logger = logging.getLogger("app.api.v1.endpoints.auth")
    auth_logger.info("🔐 AUTH: Test de logging de autenticación")
    
    return {
        "message": "✅ Logging test completed successfully",
        "logs_tested": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "loggers_tested": ["main", "middleware", "auth"],
        "check_logs": {
            "docker": "docker-compose logs -f app",
            "files": [
                "/app/logs/app.log",
                "/app/logs/http.log", 
                "/app/logs/auth.log",
                "/app/logs/errors.log"
            ]
        }
    }

if __name__ == "__main__":
    # Solo para desarrollo local
    import uvicorn
    
    logger.info("🔥 Iniciando servidor de desarrollo...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )