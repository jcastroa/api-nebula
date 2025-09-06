# ==========================================
# app/api/v1/endpoints/users.py - Endpoints de usuarios
# ==========================================

"""Endpoints para gestión de usuarios"""
from app.services.auth_service import AuthService
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
import logging

from app.schemas.user import (
    UserResponse, 
    UserCreate, 
    UserUpdate, 
    PasswordChangeRequest,
    UserListResponse
)
from app.schemas.response import SuccessResponse
from app.crud.user import UserCRUD
from app.dependencies import get_auth_service, get_current_user, get_user_crud, get_admin_user
from app.core.security import verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users")

@router.get("/", response_model=UserListResponse)
async def get_users(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=1000, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search in username/email/name"),
    is_admin: Optional[bool] = Query(None, description="Filter by admin status"),
    admin_user: dict = Depends(get_admin_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Obtener lista de usuarios (solo administradores)
    """
    try:
        # Preparar filtros
        filters = {}
        if search:
            filters['search'] = search.strip()
        if is_admin is not None:
            filters['is_admin'] = is_admin
        
        # Obtener usuarios y total
        users = await user_crud.get_multi(skip=skip, limit=limit, filters=filters)
        total = await user_crud.count(filters=filters)
        
        return UserListResponse(
            users=[UserResponse(**user) for user in users],
            total=total,
            page=skip // limit + 1,
            size=len(users)
        )
        
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail="Error fetching users")

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Obtener usuario específico
    - Usuarios pueden ver su propia información
    - Admins pueden ver cualquier usuario
    """
    try:
        # Verificar permisos
        if current_user['id'] != user_id and not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Obtener usuario
        user = await user_crud.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching user")

@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    admin_user: dict = Depends(get_admin_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Crear nuevo usuario (solo administradores)
    """
    try:
        # Verificar que username no existe
        if await user_crud.username_exists(user_data.username):
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Verificar que email no existe
        if await user_crud.email_exists(user_data.email):
            raise HTTPException(status_code=400, detail="Email already exists")
        
        # Crear usuario
        user = await user_crud.create(user_data.dict())
        if not user:
            raise HTTPException(status_code=500, detail="Error creating user")
        
        logger.info(f"User {user['username']} created by admin {admin_user['username']}")
        
        return UserResponse(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Error creating user")

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Actualizar usuario
    - Usuarios pueden actualizar su propia información (campos limitados)
    - Admins pueden actualizar cualquier usuario
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verificar permisos
        is_own_profile = current_user['id'] == user_id
        is_admin = current_user.get('is_admin', False)
        
        if not is_own_profile and not is_admin:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Si no es admin, limitar campos actualizables
        if not is_admin:
            # Usuarios normales solo pueden actualizar email, first_name, last_name
            allowed_fields = {'email', 'first_name', 'last_name'}
            update_fields = set(user_data.dict(exclude_unset=True).keys())
            
            if not update_fields.issubset(allowed_fields):
                forbidden_fields = update_fields - allowed_fields
                raise HTTPException(
                    status_code=403, 
                    detail=f"Cannot update fields: {list(forbidden_fields)}"
                )
        
        # Verificar email único si se está actualizando
        if user_data.email:
            if await user_crud.email_exists(user_data.email, exclude_id=user_id):
                raise HTTPException(status_code=400, detail="Email already exists")
        
        # Actualizar usuario
        updated_user = await user_crud.update(user_id, user_data.dict(exclude_unset=True))
        if not updated_user:
            raise HTTPException(status_code=500, detail="Error updating user")
        
        logger.info(f"User {user_id} updated by {current_user['username']}")
        
        return UserResponse(**updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error updating user")

@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user(
    user_id: int,
    admin_user: dict = Depends(get_admin_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Eliminar usuario (solo administradores)
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # No permitir auto-eliminación
        if admin_user['id'] == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
        # Eliminar usuario (soft delete)
        success = await user_crud.delete(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Error deleting user")
        
        logger.info(f"User {user_id} deleted by admin {admin_user['username']}")
        
        return SuccessResponse(message="User deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error deleting user")

@router.post("/change-password", response_model=SuccessResponse)
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Cambiar contraseña del usuario actual
    """
    try:
        # Obtener usuario con password hash
        user_with_password = await user_crud.get_by_username(current_user['username'])
        if not user_with_password:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verificar contraseña actual
        if not verify_password(password_data.current_password, user_with_password['password_hash']):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Cambiar contraseña
        success = await user_crud.change_password(current_user['id'], password_data.new_password)
        if not success:
            raise HTTPException(status_code=500, detail="Error changing password")
        
        logger.info(f"Password changed for user {current_user['username']}")
        
        return SuccessResponse(message="Password changed successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        raise HTTPException(status_code=500, detail="Error changing password")

@router.get("/{user_id}/sessions")
async def get_user_sessions(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Obtener sesiones de un usuario
    - Usuarios pueden ver sus propias sesiones
    - Admins pueden ver sesiones de cualquier usuario
    """
    try:
        # Verificar permisos
        if current_user['id'] != user_id and not current_user.get('is_admin', False):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Obtener sesiones
        sessions = await auth_service.get_user_sessions(user_id, include_inactive=True)
        
        # Filtrar información sensible para usuarios normales
        if not current_user.get('is_admin', False):
            safe_sessions = []
            for session in sessions:
                safe_sessions.append({
                    "session_id": session["session_id"],
                    "ip_address": session["ip_address"],
                    "device_info": session.get("device_info", {}),
                    "created_at": session["created_at"],
                    "last_activity": session["last_activity"],
                    "status": session["status"]
                })
            return {"sessions": safe_sessions}
        else:
            return {"sessions": sessions}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sessions for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching user sessions")

@router.post("/{user_id}/revoke-sessions", response_model=SuccessResponse)
async def revoke_user_sessions_admin(
    user_id: int,
    reason: str = Query(..., description="Reason for revocation"),
    admin_user: dict = Depends(get_admin_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revocar todas las sesiones de un usuario específico (solo administradores)
    """
    try:
        # Verificar que el usuario existe
        user_crud = UserCRUD()
        target_user = await user_crud.get(user_id)
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # No permitir revocar sesiones de otro admin (seguridad adicional)
        if target_user.get('is_admin', False) and admin_user['id'] != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Cannot revoke sessions of another administrator"
            )
        
        # Revocar todas las sesiones del usuario
        revoked_count = await auth_service.revoke_all_user_sessions(
            user_id, 
            f"admin:{reason}"
        )
        
        logger.info(
            f"All sessions for user {user_id} ({target_user['username']}) "
            f"revoked by admin {admin_user['username']}: {reason}"
        )
        
        return SuccessResponse(
            message=f"Revoked {revoked_count} sessions for user {target_user['username']}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking sessions for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error revoking user sessions")

@router.post("/{user_id}/force-logout", response_model=SuccessResponse)
async def force_logout_user(
    user_id: int,
    admin_user: dict = Depends(get_admin_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Forzar logout de un usuario (revocar todas sus sesiones)
    Alias más claro para revoke_user_sessions_admin
    """
    try:
        user_crud = UserCRUD()
        target_user = await user_crud.get(user_id)
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Usar razón estándar para force logout
        revoked_count = await auth_service.revoke_all_user_sessions(
            user_id, 
            "admin:force_logout"
        )
        
        logger.info(
            f"Force logout for user {user_id} ({target_user['username']}) "
            f"by admin {admin_user['username']}"
        )
        
        return SuccessResponse(
            message=f"User {target_user['username']} has been logged out from all devices ({revoked_count} sessions)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forcing logout for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error forcing user logout")