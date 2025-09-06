# ==========================================
# app/core/logging.py - Configuración de logging
# ==========================================

"""
Configuración centralizada del sistema de logging
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(log_level: str = "INFO", log_to_file: bool = True):
    """
    Configurar el sistema de logging para toda la aplicación
    """
    
    # Crear directorio de logs si no existe
    log_dir = Path("logs")
    if log_to_file:
        log_dir.mkdir(exist_ok=True)
        
        # Asegurar permisos en Docker
        try:
            os.chmod(log_dir, 0o755)
        except (PermissionError, OSError):
            pass
    
    # ===========================================
    # FORMATOS DE LOGS
    # ===========================================
    
    # Formato detallado para archivos
    detailed_format = logging.Formatter(
        fmt="%(asctime)s | %(name)-30s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Formato simple para consola
    console_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    
    # ===========================================
    # CONFIGURAR ROOT LOGGER
    # ===========================================
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Limpiar handlers existentes para evitar duplicados
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # ===========================================
    # HANDLER PARA CONSOLA (obligatorio)
    # ===========================================
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_format)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # ===========================================
    # HANDLERS PARA ARCHIVOS (si está habilitado)
    # ===========================================
    
    if log_to_file:
        # Handler general para toda la app
        app_log_file = log_dir / "app.log"
        app_handler = logging.handlers.RotatingFileHandler(
            filename=app_log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=5,
            encoding="utf-8"
        )
        app_handler.setFormatter(detailed_format)
        app_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(app_handler)
        
        # Handler específico para requests HTTP
        http_log_file = log_dir / "http.log"
        http_handler = logging.handlers.RotatingFileHandler(
            filename=http_log_file,
            maxBytes=20 * 1024 * 1024,  # 20MB
            backupCount=3,
            encoding="utf-8"
        )
        http_handler.setFormatter(detailed_format)
        http_handler.setLevel(logging.INFO)
        
        # Logger para middleware HTTP
        http_logger = logging.getLogger("app.middleware.logging")
        http_logger.addHandler(http_handler)
        http_logger.setLevel(logging.INFO)
        http_logger.propagate = False  # No duplicar en root logger
        
        # Handler específico para autenticación
        auth_log_file = log_dir / "auth.log" 
        auth_handler = logging.handlers.RotatingFileHandler(
            filename=auth_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding="utf-8"
        )
        auth_handler.setFormatter(detailed_format)
        auth_handler.setLevel(logging.INFO)
        
        # Logger para endpoints de auth
        auth_logger = logging.getLogger("app.api.v1.endpoints.auth")
        auth_logger.addHandler(auth_handler)
        auth_logger.setLevel(logging.INFO)
        auth_logger.propagate = False
        
        # Handler para errores críticos
        error_log_file = log_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            filename=error_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setFormatter(detailed_format)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)
    
    # ===========================================
    # CONFIGURAR LOGGERS DE LIBRERÍAS EXTERNAS
    # ===========================================
    
    # Reducir verbosidad de librerías
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiomysql").setLevel(logging.WARNING)
    logging.getLogger("aioredis").setLevel(logging.WARNING)
    
    # ===========================================
    # LOG DE INICIALIZACIÓN
    # ===========================================
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("🔧 LOGGING SYSTEM INITIALIZED")
    logger.info("=" * 60)
    logger.info(f"📊 Log Level: {log_level}")
    logger.info(f"📁 Log to File: {log_to_file}")
    
    if log_to_file:
        logger.info(f"📂 Log Directory: {log_dir.absolute()}")
        logger.info("📝 Log Files:")
        logger.info("   • app.log      - General application logs")
        logger.info("   • http.log     - HTTP requests and responses") 
        logger.info("   • auth.log     - Authentication events")
        logger.info("   • errors.log   - Error logs only")
        
        # Verificar que se pueden escribir los archivos
        test_files = [
            (app_log_file, "app.log"),
            (http_log_file, "http.log"), 
            (auth_log_file, "auth.log"),
            (error_log_file, "errors.log")
        ]
        
        for log_file, name in test_files:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"# Log initialized at {datetime.utcnow().isoformat()}\n")
                logger.info(f"   ✅ {name} - OK")
            except Exception as e:
                logger.error(f"   ❌ {name} - Error: {e}")
    
    logger.info("=" * 60)
    logger.info("🚀 Logging ready for application")
    logger.info("=" * 60)

def get_logger(name: str) -> logging.Logger:
    """
    Obtener un logger configurado para un módulo específico
    """
    return logging.getLogger(name)