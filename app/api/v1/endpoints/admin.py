# ==========================================
# app/api/v1/endpoints/admin.py - Endpoints administrativos
# ==========================================

"""Endpoints administrativos para gestión del sistema"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
import logging

from app.schemas.response import SuccessResponse, AdminSessionsResponse, MetricsResponse
from app.services.auth_service import AuthService
from app.crud.session import SessionCRUD
from app.core.redis_client import redis_client
from app.dependencies import get_admin_user, get_auth_service, get_session_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")

@router.get("/sessions", response_model=AdminSessionsResponse)
async def get_all_sessions(
    status: Optional[str] = Query(None, description="Filter by status (active, expired, revoked)"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    admin_user: dict = Depends(get_admin_user),
    session_crud: SessionCRUD = Depends(get_session_crud)
):
    """
    Obtener todas las sesiones del sistema (panel administrativo)
    """
    try:
        # Preparar filtros
        filters = {}
        if status:
            filters['status'] = status
        if user_id:
            filters['user_id'] = user_id
        if ip_address:
            filters['ip_address'] = ip_address
        
        # Obtener sesiones
        sessions = await session_crud.get_multi(skip=skip, limit=limit, filters=filters)
        
        # Contar sesiones activas
        active_count = await session_crud.count({'status': 'active'})
        
        return AdminSessionsResponse(
            sessions=sessions,
            total=len(sessions),
            active_count=active_count
        )
        
    except Exception as e:
        logger.error(f"Error getting admin sessions: {e}")
        raise HTTPException(status_code=500, detail="Error fetching sessions")

@router.post("/sessions/{session_id}/revoke", response_model=SuccessResponse)
async def revoke_session_admin(
    session_id: str,
    reason: str = Query(..., description="Reason for revocation"),
   # admin_user: dict = Depends(get_admin_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revocar sesión específica desde panel administrativo
    """
    try:
        success = await auth_service.revoke_session(session_id, f"admin:{reason}")
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        #logger.info(f"Session {session_id} revoked by admin {admin_user['username']}: {reason}")
        
        return SuccessResponse(message="Session revoked successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Error revoking session")

@router.post("/users/{user_id}/revoke-sessions", response_model=SuccessResponse)
async def revoke_user_sessions_admin(
    user_id: int,
    reason: str = Query(..., description="Reason for revocation"),
    admin_user: dict = Depends(get_admin_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revocar todas las sesiones de un usuario específico
    """
    try:
        revoked_count = await auth_service.revoke_all_user_sessions(
            user_id, 
            f"admin:{reason}"
        )
        
        logger.info(f"All sessions for user {user_id} revoked by admin {admin_user['username']}: {reason}")
        
        return SuccessResponse(
            message=f"Revoked {revoked_count} sessions successfully"
        )
        
    except Exception as e:
        logger.error(f"Error revoking sessions for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error revoking user sessions")