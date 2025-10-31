"""
Servicios (Services) endpoints.
Implements CRUD operations for service management with hybrid persistence.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any, List
from decimal import Decimal
import logging
import mysql.connector

from app.schemas.servicio import (
    ServicioCreateRequest,
    ServicioUpdateRequest,
    ServicioResponse,
    ServicioListResponse,
    ServicioSaveResponse,
    ServicioDeleteResponse
)
from app.services.servicio_service import ServicioService
from app.services.firestore_service import FirestoreService
from app.dependencies import get_current_user, get_firestore_service


router = APIRouter(prefix="/configuracion/servicios", tags=["servicios"])
logger = logging.getLogger(__name__)


def get_servicio_service(
    firestore_service: FirestoreService = Depends(get_firestore_service)
) -> ServicioService:
    """Dependency to get servicio service"""
    return ServicioService(firestore_service)


def get_negocio_id_from_user(current_user: Dict[str, Any]) -> int:
    """
    Extract negocio_id from current user.
    This assumes the user has a consultorio/negocio associated.

    Args:
        current_user: Current authenticated user

    Returns:
        negocio_id (consultorio_id)

    Raises:
        HTTPException: If user doesn't have an associated negocio
    """
    # Try different possible field names for consultorio/negocio ID
    negocio_id = (
        current_user.get('ultimo_consultorio_activo') or
        current_user.get('consultorio_id_principal')
    )

    if not negocio_id:
        logger.warning(f"User {current_user.get('id')} has no associated consultorio/negocio")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene un consultorio asociado. "
                   "Por favor contacte al administrador."
        )

    return int(negocio_id)


@router.get(
    "/",
    response_model=ServicioListResponse,
    summary="Listar servicios",
    description="Obtiene la lista de servicios activos del consultorio del usuario autenticado."
)
async def listar_servicios(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all active services for the authenticated user's business.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: List of services returned
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /configuracion/servicios/ - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # Get services from MariaDB
        conn = mysql.connector.connect(
            host=getattr(settings, 'DB_HOST', os.getenv('DB_HOST')),
            port=int(getattr(settings, 'DB_PORT', os.getenv('DB_PORT', 3306))),
            user=getattr(settings, 'DB_USER', os.getenv('DB_USER')),
            password=getattr(settings, 'DB_PASSWORD', os.getenv('DB_PASSWORD')),
            database=getattr(settings, 'DB_NAME', os.getenv('DB_NAME')),
            charset='utf8mb4',
            buffered=True
        )

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                id,
                negocio_id,
                nombre,
                descripcion,
                duracion_minutos,
                precio,
                activo,
                eliminado,
                created_at,
                updated_at,
                created_by,
                updated_by
            FROM servicios
            WHERE negocio_id = %s AND eliminado = FALSE
            ORDER BY created_at DESC
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert Decimal to float for JSON serialization
        for row in results:
            if row.get('precio') is not None:
                row['precio'] = float(row['precio'])

        # Convert to response models
        servicios = [ServicioResponse(**row) for row in results]

        return ServicioListResponse(
            servicios=servicios,
            total=len(servicios)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error listing services: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la lista de servicios"
        )


@router.post(
    "/",
    response_model=ServicioSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear servicio",
    description=(
        "Crea un nuevo servicio para el consultorio del usuario autenticado. "
        "Implementa estrategia híbrida: persiste en MariaDB (datos completos) y "
        "Firestore (precios_cita). Usa transacciones para garantizar consistencia."
    )
)
async def crear_servicio(
    payload: ServicioCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    servicio_service: ServicioService = Depends(get_servicio_service)
):
    """
    Create a new service with hybrid persistence (MariaDB + Firestore).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `nombre`: Service name (required)
    - `descripcion`: Service description (optional)
    - `duracion_minutos`: Duration in minutes (default: 30)
    - `precio`: Service price (required)
    - `activo`: Active status (default: true)

    **Response**:
    - 201: Service created successfully
    - 400: Invalid request payload
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 422: Validation error
    - 500: Internal server error (transaction rolled back)
    """
    conn = None
    mariadb_success = False

    try:
        # Get negocio_id and user_id
        negocio_id = get_negocio_id_from_user(current_user)
        user_id = current_user.get('id')

        logger.info(
            f"POST /configuracion/servicios/ - User: {user_id}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # ==========================================
        # STEP 1: MariaDB Operation (within transaction)
        # ==========================================
        conn = mysql.connector.connect(
            host=getattr(settings, 'DB_HOST', os.getenv('DB_HOST')),
            port=int(getattr(settings, 'DB_PORT', os.getenv('DB_PORT', 3306))),
            user=getattr(settings, 'DB_USER', os.getenv('DB_USER')),
            password=getattr(settings, 'DB_PASSWORD', os.getenv('DB_PASSWORD')),
            database=getattr(settings, 'DB_NAME', os.getenv('DB_NAME')),
            charset='utf8mb4',
            autocommit=False,
            buffered=True
        )

        cursor = conn.cursor(dictionary=True)

        # Create service in MariaDB
        result = await servicio_service.create_servicio_with_transaction(
            conn=conn,
            cursor=cursor,
            negocio_id=negocio_id,
            nombre=payload.nombre,
            descripcion=payload.descripcion,
            duracion_minutos=payload.duracion_minutos,
            precio=payload.precio,
            activo=payload.activo,
            user_id=user_id
        )

        logger.info(f"Service created in MariaDB: id={result['id']}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active services for this negocio
            all_services = await servicio_service.get_all_active_services(cursor, negocio_id)

            # Sync to Firestore
            await servicio_service.sync_all_services_to_firestore(negocio_id, all_services)

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as firestore_error:
            # Firestore failed - ROLLBACK MariaDB
            logger.error(f"Firestore sync failed: {str(firestore_error)}")
            conn.rollback()
            cursor.close()
            conn.close()
            logger.warning(f"MariaDB transaction rolled back for negocio_id {negocio_id}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al sincronizar con Firestore. La transacción ha sido revertida."
            )

        # ==========================================
        # STEP 3: Commit if both operations succeeded
        # ==========================================
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Transaction committed successfully for service id={result['id']}")

        # Return success response
        return ServicioSaveResponse(
            success=True,
            message="Servicio creado exitosamente",
            data=ServicioResponse(**result)
        )

    except HTTPException:
        raise

    except mysql.connector.Error as db_error:
        logger.error(f"MariaDB operation failed: {str(db_error)}")
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar en la base de datos"
        )

    except Exception as e:
        logger.error(f"Error creating service: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el servicio"
        )


@router.put(
    "/{servicio_id}/",
    response_model=ServicioSaveResponse,
    summary="Actualizar servicio",
    description="Actualiza un servicio existente con sincronización híbrida MariaDB + Firestore."
)
async def actualizar_servicio(
    servicio_id: int,
    payload: ServicioUpdateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    servicio_service: ServicioService = Depends(get_servicio_service)
):
    """
    Update an existing service with hybrid persistence.

    **Authentication required**: Yes

    **Response**:
    - 200: Service updated successfully
    - 404: Service not found
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    conn = None
    mariadb_success = False

    try:
        negocio_id = get_negocio_id_from_user(current_user)
        user_id = current_user.get('id')

        logger.info(
            f"PUT /configuracion/servicios/{servicio_id}/ - User: {user_id}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # ==========================================
        # STEP 1: MariaDB Operation
        # ==========================================
        conn = mysql.connector.connect(
            host=getattr(settings, 'DB_HOST', os.getenv('DB_HOST')),
            port=int(getattr(settings, 'DB_PORT', os.getenv('DB_PORT', 3306))),
            user=getattr(settings, 'DB_USER', os.getenv('DB_USER')),
            password=getattr(settings, 'DB_PASSWORD', os.getenv('DB_PASSWORD')),
            database=getattr(settings, 'DB_NAME', os.getenv('DB_NAME')),
            charset='utf8mb4',
            autocommit=False,
            buffered=True
        )

        cursor = conn.cursor(dictionary=True)

        # Update service
        result = await servicio_service.update_servicio_with_transaction(
            conn=conn,
            cursor=cursor,
            servicio_id=servicio_id,
            negocio_id=negocio_id,
            nombre=payload.nombre,
            descripcion=payload.descripcion,
            duracion_minutos=payload.duracion_minutos,
            precio=payload.precio,
            activo=payload.activo,
            user_id=user_id
        )

        if not result:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Servicio no encontrado"
            )

        logger.info(f"Service updated in MariaDB: id={servicio_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active services
            all_services = await servicio_service.get_all_active_services(cursor, negocio_id)

            # Sync to Firestore
            await servicio_service.sync_all_services_to_firestore(negocio_id, all_services)

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as firestore_error:
            logger.error(f"Firestore sync failed: {str(firestore_error)}")
            conn.rollback()
            cursor.close()
            conn.close()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al sincronizar con Firestore. La transacción ha sido revertida."
            )

        # ==========================================
        # STEP 3: Commit
        # ==========================================
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Transaction committed for service id={servicio_id}")

        return ServicioSaveResponse(
            success=True,
            message="Servicio actualizado exitosamente",
            data=ServicioResponse(**result)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error updating service: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el servicio"
        )


@router.delete(
    "/{servicio_id}/",
    response_model=ServicioDeleteResponse,
    summary="Eliminar servicio",
    description="Elimina (soft delete) un servicio con sincronización híbrida."
)
async def eliminar_servicio(
    servicio_id: int,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    servicio_service: ServicioService = Depends(get_servicio_service)
):
    """
    Soft delete a service (set eliminado=TRUE) with Firestore sync.

    **Authentication required**: Yes

    **Response**:
    - 200: Service deleted successfully
    - 404: Service not found
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    conn = None
    mariadb_success = False

    try:
        negocio_id = get_negocio_id_from_user(current_user)
        user_id = current_user.get('id')

        logger.info(
            f"DELETE /configuracion/servicios/{servicio_id}/ - User: {user_id}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # ==========================================
        # STEP 1: MariaDB Operation
        # ==========================================
        conn = mysql.connector.connect(
            host=getattr(settings, 'DB_HOST', os.getenv('DB_HOST')),
            port=int(getattr(settings, 'DB_PORT', os.getenv('DB_PORT', 3306))),
            user=getattr(settings, 'DB_USER', os.getenv('DB_USER')),
            password=getattr(settings, 'DB_PASSWORD', os.getenv('DB_PASSWORD')),
            database=getattr(settings, 'DB_NAME', os.getenv('DB_NAME')),
            charset='utf8mb4',
            autocommit=False,
            buffered=True
        )

        cursor = conn.cursor(dictionary=True)

        # Delete service
        deleted = await servicio_service.delete_servicio_with_transaction(
            conn=conn,
            cursor=cursor,
            servicio_id=servicio_id,
            negocio_id=negocio_id,
            user_id=user_id
        )

        if not deleted:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Servicio no encontrado"
            )

        logger.info(f"Service soft deleted in MariaDB: id={servicio_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get remaining active services
            all_services = await servicio_service.get_all_active_services(cursor, negocio_id)

            # Sync to Firestore (will remove deleted service from precios_cita)
            await servicio_service.sync_all_services_to_firestore(negocio_id, all_services)

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as firestore_error:
            logger.error(f"Firestore sync failed: {str(firestore_error)}")
            conn.rollback()
            cursor.close()
            conn.close()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al sincronizar con Firestore. La transacción ha sido revertida."
            )

        # ==========================================
        # STEP 3: Commit
        # ==========================================
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Transaction committed for service deletion id={servicio_id}")

        return ServicioDeleteResponse(
            success=True,
            message="Servicio eliminado exitosamente"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting service: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar el servicio"
        )
