# ==========================================
# app/api/v1/endpoints/assignments.py - Endpoints de asignaciones
# ==========================================

"""Endpoints para gestión de asignaciones de usuarios a negocios"""
from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List
import logging

from app.schemas.user import AssignmentCreate, AssignmentUpdate, AssignmentResponse
from app.schemas.response import SuccessResponse
from app.crud.assignment import AssignmentCRUD
from app.crud.user import UserCRUD
from app.services.consultorio_service import ConsultorioService
from app.crud.role import RoleCRUD
from app.dependencies import get_current_user, get_assignment_crud, get_user_crud, get_role_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usuarios")

@router.post("/asignaciones", response_model=AssignmentResponse)
async def create_assignment(
    assignment_data: AssignmentCreate,
    current_user: dict = Depends(get_current_user),
    assignment_crud: AssignmentCRUD = Depends(get_assignment_crud),
    user_crud: UserCRUD = Depends(get_user_crud),
    role_crud: RoleCRUD = Depends(get_role_crud)
):
    """
    Crear asignación de usuario a negocio
    """
    try:
        # Verificar que el usuario existe
        user = await user_crud.get(assignment_data.usuario_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verificar que el consultorio existe
        consultorio = ConsultorioService.get_consultorio_by_id(assignment_data.negocio_id)
        if not consultorio:
            raise HTTPException(status_code=404, detail="Business not found")

        # Verificar que el rol existe
        role = await role_crud.get(assignment_data.rol_id)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        # Crear asignación
        assignment = await assignment_crud.create(assignment_data.dict())
        if not assignment:
            raise HTTPException(
                status_code=400,
                detail="User is already assigned to this business or error creating assignment"
            )

        logger.info(
            f"Assignment created: User {assignment_data.usuario_id} -> "
            f"Business {assignment_data.negocio_id} by {current_user['username']}"
        )

        return AssignmentResponse(**assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating assignment: {e}")
        raise HTTPException(status_code=500, detail="Error creating assignment")

@router.get("/{user_id}/asignaciones", response_model=List[AssignmentResponse])
async def get_user_assignments(
    user_id: int = Path(..., gt=0, description="User ID"),
    current_user: dict = Depends(get_current_user),
    assignment_crud: AssignmentCRUD = Depends(get_assignment_crud),
    user_crud: UserCRUD = Depends(get_user_crud)
):
    """
    Obtener asignaciones de un usuario
    """
    try:
        # Verificar que el usuario existe
        user = await user_crud.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Obtener asignaciones
        assignments = await assignment_crud.get_by_user(user_id)

        return [AssignmentResponse(**assignment) for assignment in assignments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignments for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching user assignments")

@router.put("/asignaciones/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: int = Path(..., gt=0, description="Assignment ID"),
    assignment_data: AssignmentUpdate = None,
    current_user: dict = Depends(get_current_user),
    assignment_crud: AssignmentCRUD = Depends(get_assignment_crud),
    role_crud: RoleCRUD = Depends(get_role_crud)
):
    """
    Actualizar asignación
    """
    try:
        # Verificar que la asignación existe
        existing_assignment = await assignment_crud.get(assignment_id)
        if not existing_assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

        # Verificar que el rol existe si se está actualizando
        if assignment_data.rol_id:
            role = await role_crud.get(assignment_data.rol_id)
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")

        # Actualizar asignación
        updated_assignment = await assignment_crud.update(
            assignment_id,
            assignment_data.dict(exclude_unset=True)
        )
        if not updated_assignment:
            raise HTTPException(status_code=500, detail="Error updating assignment")

        logger.info(
            f"Assignment {assignment_id} updated by {current_user['username']}"
        )

        return AssignmentResponse(**updated_assignment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating assignment {assignment_id}: {e}")
        raise HTTPException(status_code=500, detail="Error updating assignment")

@router.patch("/asignaciones/{assignment_id}/activar", response_model=SuccessResponse)
async def activate_assignment(
    assignment_id: int = Path(..., gt=0, description="Assignment ID"),
    current_user: dict = Depends(get_current_user),
    assignment_crud: AssignmentCRUD = Depends(get_assignment_crud)
):
    """
    Activar asignación
    """
    try:
        # Verificar que la asignación existe
        existing_assignment = await assignment_crud.get(assignment_id)
        if not existing_assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

        # Verificar si ya está activa
        if existing_assignment['estado'] == 'activo':
            raise HTTPException(status_code=400, detail="Assignment is already active")

        # Activar asignación
        updated_assignment = await assignment_crud.activate(assignment_id)
        if not updated_assignment:
            raise HTTPException(status_code=500, detail="Error activating assignment")

        logger.info(
            f"Assignment {assignment_id} activated by {current_user['username']}"
        )

        return SuccessResponse(message="Assignment activated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating assignment {assignment_id}: {e}")
        raise HTTPException(status_code=500, detail="Error activating assignment")

@router.patch("/asignaciones/{assignment_id}/desactivar", response_model=SuccessResponse)
async def deactivate_assignment(
    assignment_id: int = Path(..., gt=0, description="Assignment ID"),
    current_user: dict = Depends(get_current_user),
    assignment_crud: AssignmentCRUD = Depends(get_assignment_crud)
):
    """
    Desactivar asignación
    """
    try:
        # Verificar que la asignación existe
        existing_assignment = await assignment_crud.get(assignment_id)
        if not existing_assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

        # Verificar si ya está inactiva
        if existing_assignment['estado'] == 'inactivo':
            raise HTTPException(status_code=400, detail="Assignment is already inactive")

        # Desactivar asignación
        updated_assignment = await assignment_crud.deactivate(assignment_id)
        if not updated_assignment:
            raise HTTPException(status_code=500, detail="Error deactivating assignment")

        logger.info(
            f"Assignment {assignment_id} deactivated by {current_user['username']}"
        )

        return SuccessResponse(message="Assignment deactivated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating assignment {assignment_id}: {e}")
        raise HTTPException(status_code=500, detail="Error deactivating assignment")
