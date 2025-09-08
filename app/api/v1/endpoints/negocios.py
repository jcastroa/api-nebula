# ==========================================
# app/api/v1/endpoints/negocios.py - Endpoints para negocios
# ==========================================

"""Endpoints para gestión de solicitudes por negocio"""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any
import logging
import json
from datetime import datetime

from app.services.firestore_service import FirestoreService
from app.websocket.websocket_manager import websocket_manager
from app.workers.monitoring_worker import firestore_monitoring_worker
from app.dependencies import get_current_user
from app.schemas.response import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negocios")

# Dependencia para obtener el servicio de Firestore
def get_firestore_service() -> FirestoreService:
    return FirestoreService()

@router.get("/{codigo_negocio}/solicitudes")
async def get_solicitudes_negocio(
    codigo_negocio: str,
    limit: int = Query(50, ge=1, le=200, description="Límite de registros"),
    last_doc_id: Optional[str] = Query(None, description="ID del último documento para paginación"),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Obtener solicitudes de un negocio específico
    
    - Requiere autenticación
    - Soporta paginación
    - Retorna datos desde Firestore
    """
    try:
        # TODO: Verificar que el usuario tenga acceso al negocio
        # Por ahora permitimos acceso, pero deberías agregar validación según tu lógica de negocio
        
        logger.info(f"Getting solicitudes for negocio {codigo_negocio} by user {current_user['id']}")
        
        # Obtener datos desde Firestore
        result = await firestore_service.get_solicitudes_by_negocio(
            codigo_negocio=codigo_negocio,
            limit=limit,
            last_doc_id=last_doc_id
        )
        
        return {
            "success": True,
            "data": result,
            "message": f"Solicitudes retrieved for negocio {codigo_negocio}"
        }
        
    except Exception as e:
        logger.error(f"Error getting solicitudes for negocio {codigo_negocio}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving solicitudes: {str(e)}")

@router.get("/{codigo_negocio}/refresh")
async def refresh_solicitudes_negocio(
    codigo_negocio: str,
    limit: int = Query(100, ge=1, le=500, description="Límite de registros para refresh"),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Endpoint de refresh - Obtiene datos actualizados desde Firestore
    
    - Este endpoint es llamado por el frontend cuando recibe notificación WebSocket
    - Retorna datos frescos directamente desde Firestore
    """
    try:
        logger.info(f"Refresh requested for negocio {codigo_negocio} by user {current_user['id']}")
        
        # Obtener datos frescos desde Firestore
        result = await firestore_service.get_solicitudes_by_negocio(
            codigo_negocio=codigo_negocio,
            limit=limit,
            last_doc_id=None  # No paginación en refresh
        )
        
        # Agregar metadata de refresh
        result["refresh_info"] = {
            "refreshed_at": datetime.utcnow().isoformat(),
            "requested_by": current_user['id'],
            "source": "firestore_direct"
        }
        
        logger.info(f"Refresh completed for negocio {codigo_negocio}: {result['returned_count']} records")
        
        return {
            "success": True,
            "data": result,
            "message": f"Data refreshed for negocio {codigo_negocio}"
        }
        
    except Exception as e:
        logger.error(f"Error refreshing solicitudes for negocio {codigo_negocio}: {e}")
        raise HTTPException(status_code=500, detail=f"Error refreshing data: {str(e)}")

@router.get("/{codigo_negocio}/solicitudes/{solicitud_id}")
async def get_solicitud_by_id(
    codigo_negocio: str,
    solicitud_id: str,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """Obtener solicitud específica por ID"""
    try:
        solicitud = await firestore_service.get_solicitud_by_id(solicitud_id)
        
        if not solicitud:
            raise HTTPException(status_code=404, detail="Solicitud not found")
        
        # Verificar que la solicitud pertenece al negocio
        if solicitud.get("codigo_negocio") != codigo_negocio:
            raise HTTPException(status_code=403, detail="Solicitud does not belong to this negocio")
        
        return {
            "success": True,
            "data": solicitud,
            "message": "Solicitud retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting solicitud {solicitud_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving solicitud: {str(e)}")

@router.put("/{codigo_negocio}/solicitudes/{solicitud_id}")
async def update_solicitud(
    codigo_negocio: str,
    solicitud_id: str,
    update_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Actualizar solicitud por ID
    
    - Actualiza directamente en Firestore
    - El worker detectará el cambio en el próximo ciclo
    """
    try:
        # Primero verificar que la solicitud existe y pertenece al negocio
        existing_solicitud = await firestore_service.get_solicitud_by_id(solicitud_id)
        
        if not existing_solicitud:
            raise HTTPException(status_code=404, detail="Solicitud not found")
        
        if existing_solicitud.get("codigo_negocio") != codigo_negocio:
            raise HTTPException(status_code=403, detail="Solicitud does not belong to this negocio")
        
        # Agregar información de auditoría
        update_data["updated_by"] = current_user['id']
        update_data["updated_by_username"] = current_user.get('username', 'unknown')
        
        # Actualizar en Firestore
        success = await firestore_service.update_solicitud(solicitud_id, update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update solicitud")
        
        logger.info(f"Solicitud {solicitud_id} updated by user {current_user['id']}")
        
        return {
            "success": True,
            "message": "Solicitud updated successfully",
            "updated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating solicitud {solicitud_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating solicitud: {str(e)}")

@router.post("/{codigo_negocio}/solicitudes")
async def create_solicitud(
    codigo_negocio: str,
    solicitud_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Crear nueva solicitud
    
    - Crea directamente en Firestore
    - El worker detectará el cambio en el próximo ciclo
    """
    try:
        # Asegurar que el codigo_negocio coincida
        solicitud_data["codigo_negocio"] = codigo_negocio
        
        # Agregar información de auditoría
        solicitud_data["created_by"] = current_user['id']
        solicitud_data["created_by_username"] = current_user.get('username', 'unknown')
        solicitud_data["deleted"] = False
        
        # Crear en Firestore
        doc_id = await firestore_service.create_solicitud(solicitud_data)
        
        logger.info(f"New solicitud created with ID {doc_id} by user {current_user['id']}")
        
        return {
            "success": True,
            "data": {
                "id": doc_id,
                "codigo_negocio": codigo_negocio
            },
            "message": "Solicitud created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating solicitud: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating solicitud: {str(e)}")

@router.delete("/{codigo_negocio}/solicitudes/{solicitud_id}")
async def delete_solicitud(
    codigo_negocio: str,
    solicitud_id: str,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Eliminar solicitud (soft delete)
    
    - Marca como eliminada en Firestore
    - El worker detectará el cambio en el próximo ciclo
    """
    try:
        # Verificar que la solicitud existe y pertenece al negocio
        existing_solicitud = await firestore_service.get_solicitud_by_id(solicitud_id)
        
        if not existing_solicitud:
            raise HTTPException(status_code=404, detail="Solicitud not found")
        
        if existing_solicitud.get("codigo_negocio") != codigo_negocio:
            raise HTTPException(status_code=403, detail="Solicitud does not belong to this negocio")
        
        # Soft delete
        success = await firestore_service.delete_solicitud(solicitud_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete solicitud")
        
        logger.info(f"Solicitud {solicitud_id} deleted by user {current_user['id']}")
        
        return {
            "success": True,
            "message": "Solicitud deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting solicitud {solicitud_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting solicitud: {str(e)}")

@router.get("/{codigo_negocio}/search")
async def search_solicitudes(
    codigo_negocio: str,
    status: Optional[str] = Query(None, description="Filtrar por status"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    prioridad: Optional[str] = Query(None, description="Filtrar por prioridad"),
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados"),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """Buscar solicitudes con filtros"""
    try:
        # Construir filtros
        filters = {}
        if status:
            filters["status"] = status
        if tipo:
            filters["tipo"] = tipo
        if prioridad:
            filters["prioridad"] = prioridad
        
        # Buscar en Firestore
        solicitudes = await firestore_service.search_solicitudes(
            codigo_negocio=codigo_negocio,
            filters=filters,
            limit=limit
        )
        
        return {
            "success": True,
            "data": {
                "solicitudes": solicitudes,
                "filters_applied": filters,
                "total_returned": len(solicitudes),
                "codigo_negocio": codigo_negocio
            },
            "message": f"Search completed for negocio {codigo_negocio}"
        }
        
    except Exception as e:
        logger.error(f"Error searching solicitudes: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching solicitudes: {str(e)}")

# ==========================================
# ENDPOINTS DE MONITOREO Y ADMINISTRACIÓN
# ==========================================

@router.get("/{codigo_negocio}/monitoring/status")
async def get_negocio_monitoring_status(
    codigo_negocio: str,
    current_user: dict = Depends(get_current_user)
):
    """Obtener estado de monitoreo para un negocio específico"""
    try:
        # Estado general del worker
        monitoring_status = firestore_monitoring_worker.get_monitoring_status()
        
        # Conexiones WebSocket para este negocio
        connected_users = websocket_manager.get_negocio_connections(codigo_negocio)
        
        # Conteo actual desde Redis
        from app.core.redis_client import redis_client
        redis_key = f"firestore_count:{codigo_negocio}"
        cached_count = redis_client.get_json(redis_key)
        
        return {
            "success": True,
            "data": {
                "codigo_negocio": codigo_negocio,
                "monitoring_active": monitoring_status.get("worker_running", False),
                "cached_count": cached_count,
                "connected_users": len(connected_users),
                "connected_user_ids": connected_users,
                "last_update": monitoring_status.get("last_update"),
                "is_monitored": codigo_negocio in monitoring_status.get("known_negocios", [])
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting monitoring status for negocio {codigo_negocio}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting monitoring status: {str(e)}")

@router.post("/monitoring/force-check")
async def force_monitoring_check(
    current_user: dict = Depends(get_current_user)
):
    """
    Forzar verificación inmediata del worker de monitoreo
    (Solo para testing/admin)
    """
    try:
        # TODO: Verificar que el usuario sea admin
        if not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await firestore_monitoring_worker.force_check()
        
        return {
            "success": True,
            "data": result,
            "message": "Force check completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in force monitoring check: {e}")
        raise HTTPException(status_code=500, detail=f"Error in force check: {str(e)}")

@router.get("/monitoring/global-status")
async def get_global_monitoring_status(
    current_user: dict = Depends(get_current_user)
):
    """Obtener estado global de monitoreo (admin)"""
    try:
        if not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        status = firestore_monitoring_worker.get_monitoring_status()
        
        return {
            "success": True,
            "data": status,
            "message": "Global monitoring status retrieved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting global monitoring status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")

# ==========================================
# WEBSOCKET ENDPOINT
# ==========================================

@router.websocket("/{codigo_negocio}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    codigo_negocio: str,
    token: str = Query(..., description="Access token para autenticación")
):
    """
    Endpoint WebSocket para notificaciones en tiempo real por negocio
    
    - Requiere token de autenticación en query parameter
    - Solo recibe notificaciones del negocio específico
    """
    try:
        # Verificar token de autenticación
        from app.core.security import verify_token
        from app.dependencies import get_user_crud
        
        try:
            payload = verify_token(token)
            user_crud = get_user_crud()
            user = await user_crud.get(payload['user_id'])
            
            if not user:
                await websocket.close(code=4001, reason="Invalid user")
                return
                
        except Exception as e:
            logger.warning(f"WebSocket auth failed: {e}")
            await websocket.close(code=4001, reason="Authentication failed")
            return
        
        user_id = user['id']
        user_info = {
            "username": user.get('username'),
            "email": user.get('email')
        }
        
        # Conectar usuario al WebSocket
        await websocket_manager.connect(websocket, user_id, codigo_negocio, user_info)
        
        logger.info(f"🔌 WebSocket connected: user {user_id} to negocio {codigo_negocio}")
        
        try:
            # Loop para manejar mensajes del cliente
            while True:
                # Recibir mensaje del cliente
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    await websocket_manager.handle_client_message(user_id, codigo_negocio, message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from user {user_id}: {data}")
                
        except WebSocketDisconnect:
            logger.info(f"🔌 WebSocket disconnected: user {user_id} from negocio {codigo_negocio}")
        
        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")
        
        finally:
            # Limpiar conexión
            await websocket_manager.disconnect(user_id, codigo_negocio)
    
    except Exception as e:
        logger.error(f"WebSocket setup error: {e}")
        try:
            await websocket.close(code=4000, reason="Server error")
        except:
            pass