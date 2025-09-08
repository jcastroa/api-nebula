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
from app.workers.scheduler import start_background_tasks, stop_background_tasks

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
    
    # try:
    #     await start_background_tasks()
    #     logger.info("🔄 Background tasks iniciadas")
    # except Exception as e:
    #     logger.error(f"❌ Error iniciando background tasks: {e}")
    #     raise
    
    # logger.info("✅ Aplicación iniciada correctamente")
    # Verificar conexiones básicas
    try:
        # Test Redis
        from app.core.redis_client import redis_client
        if redis_client.ping():
            logger.info("✅ Redis: Conectado")
        else:
            logger.warning("⚠️  Redis: No disponible")
        
        # Test MySQL
        from app.core.database import get_db_connection
        try:
            with get_db_connection() as conn:
                logger.info("✅ MySQL: Conectado")
        except Exception as e:
            logger.warning(f"⚠️  MySQL: Error - {e}")
        
        # Test Firestore
        try:
            from app.services.firestore_service import FirestoreService
            firestore_service = FirestoreService()
            health = await firestore_service.health_check()
            if health.get("firestore_connected"):
                logger.info("✅ Firestore: Conectado")
            else:
                logger.warning("⚠️  Firestore: No disponible")
        except Exception as e:
            logger.warning(f"⚠️  Firestore: Error - {e}")
        
        # Iniciar workers de background
        await start_background_tasks()
        
        logger.info("=" * 80)
        logger.info("✅ SISTEMA INICIADO CORRECTAMENTE")
        logger.info("📡 Worker de monitoreo Firestore: ACTIVO (30s)")
        logger.info("🔌 WebSocket para notificaciones: DISPONIBLE")
        logger.info("🧹 Tareas de limpieza: PROGRAMADAS")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Error durante startup: {e}")

async def shutdown_handler():
    """Limpieza al cerrar"""
    logger.info("🛑 Cerrando aplicación...")

    try:
        # Detener workers de background
        await stop_background_tasks()
        
        logger.info("✅ Workers detenidos correctamente")
        logger.info("✅ Aplicación cerrada limpiamente")
        
    except Exception as e:
        logger.error(f"❌ Error durante shutdown: {e}")
    
    logger.info("=" * 50)

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