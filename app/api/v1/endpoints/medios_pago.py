"""
Medios de Pago (Payment Methods) endpoints.
Implements CRUD operations for payment method management with hybrid persistence.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any, List
import logging
import mysql.connector

from app.schemas.medio_pago import (
    MedioPagoCreateRequest,
    MedioPagoUpdateRequest,
    MedioPagoResponse,
    MedioPagoListResponse,
    MedioPagoSaveResponse,
    MedioPagoDeleteResponse
)
from app.services.medio_pago_service import MedioPagoService
from app.services.firestore_service import FirestoreService
from app.dependencies import get_current_user, get_firestore_service


router = APIRouter(prefix="/medios-pago", tags=["medios_pago"])
logger = logging.getLogger(__name__)


def get_medio_pago_service(
    firestore_service: FirestoreService = Depends(get_firestore_service)
) -> MedioPagoService:
    """Dependency to get medio pago service"""
    return MedioPagoService(firestore_service)


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
    response_model=MedioPagoListResponse,
    summary="Listar medios de pago",
    description="Obtiene la lista de medios de pago activos del consultorio del usuario autenticado."
)
async def listar_medios_pago(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all active payment methods for the authenticated user's business.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: List of payment methods returned
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /medios-pago/ - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # Get payment methods from MariaDB
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
                descripcion,
                detalle,
                nombre_titular,
                numero_cuenta,
                activo,
                eliminado,
                created_at,
                updated_at,
                created_by,
                updated_by
            FROM medios_pago
            WHERE negocio_id = %s AND eliminado = FALSE AND activo = TRUE
            ORDER BY created_at DESC
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert to response models
        medios_pago = [MedioPagoResponse(**row) for row in results]

        return MedioPagoListResponse(
            medios_pago=medios_pago,
            total=len(medios_pago)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error listing payment methods: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la lista de medios de pago"
        )


@router.post(
    "/",
    response_model=MedioPagoSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear medio de pago",
    description=(
        "Crea un nuevo medio de pago para el consultorio del usuario autenticado. "
        "Implementa estrategia híbrida: persiste en MariaDB (datos completos) y "
        "Firestore (medios_pago array y datos_pago map). Usa transacciones para garantizar consistencia."
    )
)
async def crear_medio_pago(
    payload: MedioPagoCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    medio_pago_service: MedioPagoService = Depends(get_medio_pago_service)
):
    """
    Create a new payment method with hybrid persistence (MariaDB + Firestore).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `descripcion`: Payment method description (required)
    - `detalle`: Payment method details (required)
    - `nombre_titular`: Account holder name (optional)
    - `numero_cuenta`: Account number (optional)

    **Response**:
    - 201: Payment method created successfully
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
            f"POST /medios-pago/ - User: {user_id}, "
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

        # Create payment method in MariaDB
        result = await medio_pago_service.create_medio_pago_with_transaction(
            conn=conn,
            cursor=cursor,
            negocio_id=negocio_id,
            descripcion=payload.descripcion,
            detalle=payload.detalle,
            nombre_titular=payload.nombre_titular,
            numero_cuenta=payload.numero_cuenta,
            user_id=user_id
        )

        logger.info(f"Payment method created in MariaDB: id={result['id']}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active payment methods for this negocio
            all_payment_methods = await medio_pago_service.get_all_active_payment_methods(
                cursor, negocio_id
            )

            # Sync to Firestore
            await medio_pago_service.sync_all_payment_methods_to_firestore(
                negocio_id, all_payment_methods
            )

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
        logger.info(f"Transaction committed successfully for payment method id={result['id']}")

        # Return success response
        return MedioPagoSaveResponse(
            success=True,
            message="Medio de pago creado exitosamente",
            data=MedioPagoResponse(**result)
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
        logger.error(f"Error creating payment method: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el medio de pago"
        )


@router.put(
    "/{medio_pago_id}/",
    response_model=MedioPagoSaveResponse,
    summary="Actualizar medio de pago",
    description="Actualiza un medio de pago existente con sincronización híbrida MariaDB + Firestore."
)
async def actualizar_medio_pago(
    medio_pago_id: int,
    payload: MedioPagoUpdateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    medio_pago_service: MedioPagoService = Depends(get_medio_pago_service)
):
    """
    Update an existing payment method with hybrid persistence.

    **Authentication required**: Yes

    **Response**:
    - 200: Payment method updated successfully
    - 404: Payment method not found
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
            f"PUT /medios-pago/{medio_pago_id}/ - User: {user_id}, "
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

        # Update payment method
        result = await medio_pago_service.update_medio_pago_with_transaction(
            conn=conn,
            cursor=cursor,
            medio_pago_id=medio_pago_id,
            negocio_id=negocio_id,
            descripcion=payload.descripcion,
            detalle=payload.detalle,
            nombre_titular=payload.nombre_titular,
            numero_cuenta=payload.numero_cuenta,
            user_id=user_id
        )

        if not result:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medio de pago no encontrado"
            )

        logger.info(f"Payment method updated in MariaDB: id={medio_pago_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active payment methods
            all_payment_methods = await medio_pago_service.get_all_active_payment_methods(
                cursor, negocio_id
            )

            # Sync to Firestore
            await medio_pago_service.sync_all_payment_methods_to_firestore(
                negocio_id, all_payment_methods
            )

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
        logger.info(f"Transaction committed for payment method id={medio_pago_id}")

        return MedioPagoSaveResponse(
            success=True,
            message="Medio de pago actualizado exitosamente",
            data=MedioPagoResponse(**result)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error updating payment method: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el medio de pago"
        )


@router.delete(
    "/{medio_pago_id}/",
    response_model=MedioPagoDeleteResponse,
    summary="Eliminar medio de pago",
    description="Elimina (soft delete) un medio de pago con sincronización híbrida."
)
async def eliminar_medio_pago(
    medio_pago_id: int,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    medio_pago_service: MedioPagoService = Depends(get_medio_pago_service)
):
    """
    Soft delete a payment method (set eliminado=TRUE and activo=FALSE) with Firestore sync.

    **Authentication required**: Yes

    **Response**:
    - 200: Payment method deleted successfully
    - 404: Payment method not found
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
            f"DELETE /medios-pago/{medio_pago_id}/ - User: {user_id}, "
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

        # Delete payment method
        deleted = await medio_pago_service.delete_medio_pago_with_transaction(
            conn=conn,
            cursor=cursor,
            medio_pago_id=medio_pago_id,
            negocio_id=negocio_id,
            user_id=user_id
        )

        if not deleted:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medio de pago no encontrado"
            )

        logger.info(f"Payment method soft deleted in MariaDB: id={medio_pago_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get remaining active payment methods
            all_payment_methods = await medio_pago_service.get_all_active_payment_methods(
                cursor, negocio_id
            )

            # Sync to Firestore (will remove deleted payment method from arrays/maps)
            await medio_pago_service.sync_all_payment_methods_to_firestore(
                negocio_id, all_payment_methods
            )

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
        logger.info(f"Transaction committed for payment method deletion id={medio_pago_id}")

        return MedioPagoDeleteResponse(
            success=True,
            message="Medio de pago eliminado exitosamente"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting payment method: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar el medio de pago"
        )
