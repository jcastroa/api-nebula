"""
Promociones (Promotions) endpoints.
Implements CRUD operations for promotion management with hybrid persistence.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any, List
from decimal import Decimal
import logging
import mysql.connector

from app.schemas.promocion import (
    PromocionCreateRequest,
    PromocionUpdateRequest,
    PromocionResponse,
    PromocionListResponse,
    PromocionSaveResponse,
    PromocionDeleteResponse
)
from app.services.promocion_service import PromocionService
from app.services.firestore_service import FirestoreService
from app.dependencies import get_current_user, get_firestore_service


router = APIRouter(prefix="/promociones", tags=["promociones"])
logger = logging.getLogger(__name__)


def get_promocion_service(
    firestore_service: FirestoreService = Depends(get_firestore_service)
) -> PromocionService:
    """Dependency to get promocion service"""
    return PromocionService(firestore_service)


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
    response_model=PromocionListResponse,
    summary="Listar promociones",
    description="Obtiene la lista de promociones activas y no eliminadas del consultorio del usuario autenticado."
)
async def listar_promociones(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all active and non-deleted promotions for the authenticated user's business.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: List of promotions returned
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /promociones/ - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # Get promotions from MariaDB
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
                titulo,
                descripcion,
                tipo_descuento,
                valor_descuento,
                fecha_inicio,
                fecha_fin,
                activo,
                eliminado,
                created_at,
                updated_at,
                created_by,
                updated_by
            FROM promociones
            WHERE negocio_id = %s AND eliminado = FALSE AND activo = TRUE
            ORDER BY fecha_inicio DESC
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert Decimal to float for JSON serialization
        for row in results:
            if row.get('valor_descuento') is not None:
                row['valor_descuento'] = float(row['valor_descuento'])

        # Convert to response models
        promociones = [PromocionResponse(**row) for row in results]

        return PromocionListResponse(
            promociones=promociones,
            total=len(promociones)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error listing promotions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la lista de promociones"
        )


@router.post(
    "/",
    response_model=PromocionSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear promoción",
    description=(
        "Crea una nueva promoción para el consultorio del usuario autenticado. "
        "Implementa estrategia híbrida: persiste en MariaDB (datos completos) y "
        "Firestore (array de promociones). Usa transacciones para garantizar consistencia."
    )
)
async def crear_promocion(
    payload: PromocionCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    promocion_service: PromocionService = Depends(get_promocion_service)
):
    """
    Create a new promotion with hybrid persistence (MariaDB + Firestore).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `titulo`: Promotion title (required)
    - `descripcion`: Promotion description (required)
    - `tipo_descuento`: Discount type: 'porcentaje' or 'monto_fijo' (required)
    - `valor_descuento`: Discount value (required)
    - `fecha_inicio`: Start date (YYYY-MM-DD) (required)
    - `fecha_fin`: End date (YYYY-MM-DD) (required)
    - `activo`: Active status (default: true)

    **Response**:
    - 201: Promotion created successfully
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
            f"POST /promociones/ - User: {user_id}, "
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

        # Create promotion in MariaDB
        result = await promocion_service.create_promocion_with_transaction(
            conn=conn,
            cursor=cursor,
            negocio_id=negocio_id,
            titulo=payload.titulo,
            descripcion=payload.descripcion,
            tipo_descuento=payload.tipo_descuento.value,
            valor_descuento=payload.valor_descuento,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            activo=payload.activo,
            user_id=user_id
        )

        logger.info(f"Promotion created in MariaDB: id={result['id']}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active promotions for this negocio
            all_promociones = await promocion_service.get_all_active_promociones(cursor, negocio_id)

            # Sync to Firestore
            await promocion_service.sync_all_promociones_to_firestore(negocio_id, all_promociones)

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
        logger.info(f"Transaction committed successfully for promotion id={result['id']}")

        # Return success response
        return PromocionSaveResponse(
            success=True,
            message="Promoción creada exitosamente",
            data=PromocionResponse(**result)
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
        logger.error(f"Error creating promotion: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la promoción"
        )


@router.put(
    "/{promocion_id}/",
    response_model=PromocionSaveResponse,
    summary="Actualizar promoción",
    description="Actualiza una promoción existente con sincronización híbrida MariaDB + Firestore."
)
async def actualizar_promocion(
    promocion_id: int,
    payload: PromocionUpdateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    promocion_service: PromocionService = Depends(get_promocion_service)
):
    """
    Update an existing promotion with hybrid persistence.

    **Authentication required**: Yes

    **Response**:
    - 200: Promotion updated successfully
    - 404: Promotion not found
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
            f"PUT /promociones/{promocion_id}/ - User: {user_id}, "
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

        # Update promotion
        result = await promocion_service.update_promocion_with_transaction(
            conn=conn,
            cursor=cursor,
            promocion_id=promocion_id,
            negocio_id=negocio_id,
            titulo=payload.titulo,
            descripcion=payload.descripcion,
            tipo_descuento=payload.tipo_descuento.value if payload.tipo_descuento else None,
            valor_descuento=payload.valor_descuento,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            activo=payload.activo,
            user_id=user_id
        )

        if not result:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Promoción no encontrada"
            )

        logger.info(f"Promotion updated in MariaDB: id={promocion_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active promotions
            all_promociones = await promocion_service.get_all_active_promociones(cursor, negocio_id)

            # Sync to Firestore
            await promocion_service.sync_all_promociones_to_firestore(negocio_id, all_promociones)

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
        logger.info(f"Transaction committed for promotion id={promocion_id}")

        return PromocionSaveResponse(
            success=True,
            message="Promoción actualizada exitosamente",
            data=PromocionResponse(**result)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error updating promotion: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la promoción"
        )


@router.delete(
    "/{promocion_id}/",
    response_model=PromocionDeleteResponse,
    summary="Eliminar promoción",
    description="Elimina (soft delete) una promoción con sincronización híbrida."
)
async def eliminar_promocion(
    promocion_id: int,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    promocion_service: PromocionService = Depends(get_promocion_service)
):
    """
    Soft delete a promotion (set eliminado=TRUE) with Firestore sync.

    **Authentication required**: Yes

    **Response**:
    - 200: Promotion deleted successfully
    - 404: Promotion not found
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
            f"DELETE /promociones/{promocion_id}/ - User: {user_id}, "
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

        # Delete promotion
        deleted = await promocion_service.delete_promocion_with_transaction(
            conn=conn,
            cursor=cursor,
            promocion_id=promocion_id,
            negocio_id=negocio_id,
            user_id=user_id
        )

        if not deleted:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Promoción no encontrada"
            )

        logger.info(f"Promotion soft deleted in MariaDB: id={promocion_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get remaining active promotions
            all_promociones = await promocion_service.get_all_active_promociones(cursor, negocio_id)

            # Sync to Firestore (will remove deleted promotion from array)
            await promocion_service.sync_all_promociones_to_firestore(negocio_id, all_promociones)

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
        logger.info(f"Transaction committed for promotion deletion id={promocion_id}")

        return PromocionDeleteResponse(
            success=True,
            message="Promoción eliminada exitosamente"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting promotion: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la promoción"
        )
