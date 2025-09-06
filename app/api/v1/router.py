# ==========================================
# app/api/v1/router.py - Router principal v1
# ==========================================

"""Router principal para API v1"""
from fastapi import APIRouter
from datetime import datetime

from app.api.v1.endpoints import auth, users, admin
from app.core.database import get_db_connection
from app.core.redis_client import redis_client
from app.config import settings

# Router principal de la API v1
api_router = APIRouter()

# Incluir todos los routers de endpoints
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(admin.router, tags=["administration"])

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Verificar estado de todos los servicios"""
    
    # Test MySQL
    mysql_status = "OK" if get_db_connection() else "ERROR"
    
    # Test Redis  
    redis_status = "OK" if redis_client.ping() else "ERROR"
    
    # Status general
    overall_status = "OK" if mysql_status == "OK" and redis_status == "OK" else "ERROR"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "services": {
            "mysql": mysql_status,
            "redis": redis_status
        },
        "environment": settings.ENVIRONMENT
    }