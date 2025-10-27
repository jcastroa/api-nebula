# ==========================================
# app/api/v1/endpoints/roles.py - Endpoints de roles
# ==========================================

"""Endpoints para gestión de roles"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import logging

from app.schemas.user import RoleResponse
from app.crud.role import RoleCRUD
from app.dependencies import get_current_user, get_role_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles")

@router.get("/", response_model=List[RoleResponse])
async def get_roles(
    current_user: dict = Depends(get_current_user),
    role_crud: RoleCRUD = Depends(get_role_crud)
):
    """
    Obtener lista de roles activos
    """
    try:
        # Obtener todos los roles activos
        roles = await role_crud.get_all_active()

        return [RoleResponse(**role) for role in roles]

    except Exception as e:
        logger.error(f"Error getting roles: {e}")
        raise HTTPException(status_code=500, detail="Error fetching roles")
