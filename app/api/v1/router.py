# ==========================================
# app/api/v1/router.py - Router principal v1
# ==========================================

"""Router principal para API v1"""
from fastapi import APIRouter
from datetime import datetime

from app.api.v1.endpoints import auth, users, admin, negocios, vinculacion, roles, assignments, chatbot, servicios, medios_pago, promociones
from app.core.database import get_db_connection
from app.core.redis_client import redis_client
from app.config import settings

# Router principal de la API v1
api_router = APIRouter()

# Incluir todos los routers de endpoints
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(admin.router, tags=["administration"])
api_router.include_router(negocios.router, tags=["negocios"])
api_router.include_router(vinculacion.router, tags=["vinculacion"])
api_router.include_router(roles.router, tags=["roles"])
api_router.include_router(assignments.router, tags=["assignments"])
api_router.include_router(chatbot.router, tags=["chatbot"])
api_router.include_router(servicios.router, tags=["servicios"])
api_router.include_router(medios_pago.router, tags=["medios_pago"])
api_router.include_router(promociones.router, tags=["promociones"])

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Verificar estado de todos los servicios"""
    
    # Test MySQL
    try:
        with get_db_connection() as conn:
            mysql_status = "OK"
    except:
        mysql_status = "ERROR"
    
    # Test Redis  
    redis_status = "OK" if redis_client.ping() else "ERROR"

    # Test Firestore
    try:
        from app.services.firestore_service import FirestoreService
        firestore_service = FirestoreService()
        firestore_health = await firestore_service.health_check()
        firestore_status = firestore_health.get("status", "ERROR")
    except Exception as e:
        firestore_status = f"ERROR: {str(e)}"
    
    # Test Worker de Monitoreo
    try:
        from app.workers.smart_monitoring_worker import firestore_monitoring_worker
        monitoring_status = "OK" if firestore_monitoring_worker.running else "STOPPED"
    except:
        monitoring_status = "ERROR"
    
    # Test WebSocket Manager
    try:
        from app.websocket.websocket_manager import websocket_manager
        ws_stats = websocket_manager.get_active_connections_stats()
        websocket_status = "OK"
    except:
        websocket_status = "ERROR"
        ws_stats = {}
    
    # Status general
    all_services = [mysql_status, redis_status, firestore_status, monitoring_status, websocket_status]
    overall_status = "OK" if all(status == "OK" for status in all_services) else "PARTIAL"
   
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "services": {
            "mysql": mysql_status,
            "redis": redis_status,
            "firestore": firestore_status,
            "monitoring_worker": monitoring_status,
            "websocket_manager": websocket_status
        },
        "websocket_stats": ws_stats,
        "environment": settings.ENVIRONMENT
    }