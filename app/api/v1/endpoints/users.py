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
from app.dependencies import get_auth_service, get_current_user, get_user_crud
from app.core.security import verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users")

@router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    limit: int = Query(50, ge=1, le=1000, description="Max records to return"),
    username: Optional[str] = Query(None, description="Search in username"),
    activo: Optional[bool] = Query(None, description="Search in activo"),
    email: Optional[str] = Query(None, description="Search in email"),
    rol_global: Optional[str] = Query(None, description="Search in rol global"),
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Obtener lista de usuarios
    """
    try:
        # Calcular skip basado en page
        skip = (page - 1) * limit

        # Preparar filtros
        filters = {}
        if username:
            filters['username'] = username.strip()
        if activo is not None:
            filters['activo'] = activo
        if email is not None:
            filters['email'] = email.strip()
        if rol_global is not None:
            filters['rol_global'] = rol_global.strip()

        print(f"📋 Filters: {filters}")

        # Obtener usuarios y total
        users = await user_crud.get_multi(skip=skip, limit=limit, filters=filters)
        total = await user_crud.count(filters=filters)

        return UserListResponse(
            users=[UserResponse(**user) for user in users],
            total=total,
            page=page,
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
    """
    try:
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
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Crear nuevo usuario
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
        
        logger.info(f"User {user['username']} created by {current_user['username']}")
        
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
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

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
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Eliminar usuario
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # No permitir auto-eliminación
        if current_user['id'] == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")

        # Eliminar usuario (soft delete)
        success = await user_crud.delete(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Error deleting user")

        logger.info(f"User {user_id} deleted by {current_user['username']}")
        
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
    """
    try:
        # Obtener sesiones
        sessions = await auth_service.get_user_sessions(user_id, include_inactive=True)

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
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revocar todas las sesiones de un usuario específico
    """
    try:
        # Verificar que el usuario existe
        user_crud = UserCRUD()
        target_user = await user_crud.get(user_id)
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Revocar todas las sesiones del usuario
        revoked_count = await auth_service.revoke_all_user_sessions(
            user_id,
            f"user:{reason}"
        )

        logger.info(
            f"All sessions for user {user_id} ({target_user['username']}) "
            f"revoked by {current_user['username']}: {reason}"
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
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Forzar logout de un usuario (revocar todas sus sesiones)
    """
    try:
        user_crud = UserCRUD()
        target_user = await user_crud.get(user_id)
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Usar razón estándar para force logout
        revoked_count = await auth_service.revoke_all_user_sessions(
            user_id,
            "user:force_logout"
        )

        logger.info(
            f"Force logout for user {user_id} ({target_user['username']}) "
            f"by {current_user['username']}"
        )
        
        return SuccessResponse(
            message=f"User {target_user['username']} has been logged out from all devices ({revoked_count} sessions)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forcing logout for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error forcing user logout")

@router.patch("/{user_id}/activar", response_model=SuccessResponse)
async def activate_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Activar usuario
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verificar si ya está activo
        if existing_user.get('is_active', False):
            raise HTTPException(status_code=400, detail="User is already active")

        # Activar usuario
        updated_user = await user_crud.update(user_id, {'is_active': True})
        if not updated_user:
            raise HTTPException(status_code=500, detail="Error activating user")

        logger.info(f"User {user_id} activated by {current_user['username']}")

        return SuccessResponse(message="User activated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error activating user")

@router.patch("/{user_id}/desactivar", response_model=SuccessResponse)
async def deactivate_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Desactivar usuario
    """
    try:
        # Verificar que el usuario existe
        existing_user = await user_crud.get(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        # No permitir auto-desactivación
        if current_user['id'] == user_id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

        # Verificar si ya está inactivo
        if not existing_user.get('is_active', True):
            raise HTTPException(status_code=400, detail="User is already inactive")

        # Desactivar usuario
        updated_user = await user_crud.update(user_id, {'is_active': False})
        if not updated_user:
            raise HTTPException(status_code=500, detail="Error deactivating user")

        logger.info(f"User {user_id} deactivated by {current_user['username']}")

        return SuccessResponse(message="User deactivated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error deactivating user")