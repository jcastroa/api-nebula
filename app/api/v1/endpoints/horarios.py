"""
Horarios (Business Hours) endpoints.
Implements CRUD operations for business hours and exceptions management with hybrid persistence.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any
import logging
import mysql.connector

from app.schemas.horario import (
    HorariosCreateRequest,
    HorariosResponse,
    HorariosSaveResponse,
    ExcepcionCreateRequest,
    ExcepcionResponse,
    ExcepcionesListResponse,
    ExcepcionSaveResponse,
    ExcepcionDeleteResponse
)
from app.services.horario_service import HorarioService
from app.services.firestore_service import FirestoreService
from app.dependencies import get_current_user, get_firestore_service


router = APIRouter(prefix="/horarios", tags=["horarios"])
logger = logging.getLogger(__name__)


def get_horario_service(
    firestore_service: FirestoreService = Depends(get_firestore_service)
) -> HorarioService:
    """Dependency to get horario service"""
    return HorarioService(firestore_service)


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


# ===== Horarios Endpoints =====

@router.get(
    "/",
    response_model=HorariosResponse,
    summary="Obtener horarios de atención",
    description="Obtiene la configuración de horarios de atención del consultorio del usuario autenticado."
)
async def obtener_horarios(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    horario_service: HorarioService = Depends(get_horario_service)
):
    """
    Get business hours configuration for the authenticated user's business.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: Business hours configuration returned
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /horarios/ - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # Get horarios from MariaDB
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

        # Get horarios configuration
        result = await horario_service.get_horarios_from_mariadb(cursor, negocio_id)

        cursor.close()
        conn.close()

        return HorariosResponse(**result)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error getting horarios: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la configuración de horarios"
        )


@router.post(
    "/",
    response_model=HorariosSaveResponse,
    summary="Guardar horarios de atención",
    description=(
        "Guarda la configuración de horarios de atención para el consultorio. "
        "Implementa estrategia híbrida: persiste en MariaDB (horarios_atencion, consultorios) y "
        "Firestore (negocios.horarios, negocios.intervalo_citas). Usa transacciones para garantizar consistencia."
    )
)
async def guardar_horarios(
    payload: HorariosCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    horario_service: HorarioService = Depends(get_horario_service)
):
    """
    Save business hours configuration with hybrid persistence (MariaDB + Firestore).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `dias_laborables`: Working days configuration (map of day name to boolean)
    - `horarios`: Business hours per day (map of day name to array of time ranges)
    - `intervalo_citas`: Appointment interval in minutes (15, 30, 45, 60, 90, 120)

    **Response**:
    - 200: Configuration saved successfully
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
            f"POST /horarios/ - User: {user_id}, "
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

        # Convert Pydantic models to dicts
        horarios_dict = {
            dia: [{'inicio': r.inicio, 'fin': r.fin} for r in rangos]
            for dia, rangos in payload.horarios.items()
        }

        # Save horarios in MariaDB
        await horario_service.save_horarios_with_transaction(
            conn=conn,
            cursor=cursor,
            negocio_id=negocio_id,
            dias_laborables=payload.dias_laborables,
            horarios=horarios_dict,
            intervalo_citas=payload.intervalo_citas,
            user_id=user_id
        )

        logger.info(f"Horarios saved in MariaDB for negocio_id {negocio_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Sync to Firestore
            await horario_service.sync_horarios_to_firestore(
                negocio_id=negocio_id,
                horarios=horarios_dict,
                intervalo_citas=payload.intervalo_citas
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
        logger.info(f"Transaction committed successfully for negocio_id {negocio_id}")

        # Return success response
        return HorariosSaveResponse(
            success=True,
            message="Configuración guardada exitosamente"
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
        logger.error(f"Error saving horarios: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al guardar la configuración de horarios"
        )


# ===== Excepciones Endpoints =====

@router.get(
    "/excepciones",
    response_model=ExcepcionesListResponse,
    summary="Listar excepciones",
    description="Obtiene la lista de excepciones (días no laborables) del consultorio."
)
async def listar_excepciones(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    horario_service: HorarioService = Depends(get_horario_service)
):
    """
    Get all exceptions (non-working days) for the authenticated user's business.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: List of exceptions returned
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /horarios/excepciones - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # Get excepciones from MariaDB
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

        # Get excepciones
        excepciones = await horario_service.get_excepciones_from_mariadb(cursor, negocio_id)

        cursor.close()
        conn.close()

        # Convert to response models
        excepciones_response = [ExcepcionResponse(**exc) for exc in excepciones]

        return ExcepcionesListResponse(excepciones=excepciones_response)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error listing excepciones: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la lista de excepciones"
        )


@router.post(
    "/excepciones",
    response_model=ExcepcionSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear excepción",
    description=(
        "Crea una nueva excepción (día no laborable) para el consultorio. "
        "Las excepciones se guardan en MariaDB (dias_no_laborables)."
    )
)
async def crear_excepcion(
    payload: ExcepcionCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    horario_service: HorarioService = Depends(get_horario_service)
):
    """
    Create a new exception (non-working day).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `tipo`: Exception type (feriado, vacaciones, otro)
    - `fechaInicio`: Start date (YYYY-MM-DD)
    - `fechaFin`: End date (YYYY-MM-DD), optional for single day
    - `motivo`: Reason for the exception

    **Response**:
    - 201: Exception created successfully
    - 400: Invalid request payload
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 422: Validation error
    - 500: Internal server error
    """
    conn = None
    mariadb_success = False

    try:
        # Get negocio_id and user_id
        negocio_id = get_negocio_id_from_user(current_user)
        user_id = current_user.get('id')

        logger.info(
            f"POST /horarios/excepciones - User: {user_id}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # ==========================================
        # MariaDB Operation (within transaction)
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

        # Create exception in MariaDB
        result = await horario_service.create_excepcion_with_transaction(
            conn=conn,
            cursor=cursor,
            negocio_id=negocio_id,
            tipo=payload.tipo.value,
            fecha_inicio=payload.fechaInicio,
            fecha_fin=payload.fechaFin,
            motivo=payload.motivo,
            user_id=user_id
        )

        logger.info(f"Exception created in MariaDB: id={result['id']}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active exceptions for this negocio
            all_excepciones = await horario_service.get_excepciones_from_mariadb(cursor, negocio_id)

            # Sync to Firestore
            await horario_service.sync_excepciones_to_firestore(negocio_id, all_excepciones)

            logger.info(f"Firestore sync successful for excepciones, negocio_id {negocio_id}")

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
        logger.info(f"Transaction committed successfully for exception id={result['id']}")

        # Return success response
        return ExcepcionSaveResponse(
            success=True,
            message="Excepción agregada exitosamente",
            excepcion=ExcepcionResponse(**result)
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
        logger.error(f"Error creating exception: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la excepción"
        )


@router.delete(
    "/excepciones/{excepcion_id}",
    response_model=ExcepcionDeleteResponse,
    summary="Eliminar excepción",
    description="Elimina (soft delete) una excepción existente."
)
async def eliminar_excepcion(
    excepcion_id: int,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    horario_service: HorarioService = Depends(get_horario_service)
):
    """
    Soft delete an exception (set eliminado=TRUE).

    **Authentication required**: Yes

    **Response**:
    - 200: Exception deleted successfully
    - 404: Exception not found
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
            f"DELETE /horarios/excepciones/{excepcion_id} - User: {user_id}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get database configuration
        from app.config import settings
        import os

        # ==========================================
        # MariaDB Operation
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

        # Delete exception
        deleted = await horario_service.delete_excepcion_with_transaction(
            conn=conn,
            cursor=cursor,
            excepcion_id=excepcion_id,
            negocio_id=negocio_id,
            user_id=user_id
        )

        if not deleted:
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Excepción no encontrada"
            )

        logger.info(f"Exception soft deleted in MariaDB: id={excepcion_id}")
        mariadb_success = True

        # ==========================================
        # STEP 2: Firestore Sync
        # ==========================================
        try:
            # Get all active exceptions (excluding the deleted one)
            all_excepciones = await horario_service.get_excepciones_from_mariadb(cursor, negocio_id)

            # Sync to Firestore (will remove deleted exception)
            await horario_service.sync_excepciones_to_firestore(negocio_id, all_excepciones)

            logger.info(f"Firestore sync successful for excepciones, negocio_id {negocio_id}")

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
        logger.info(f"Transaction committed for exception deletion id={excepcion_id}")

        return ExcepcionDeleteResponse(
            success=True,
            message="Excepción eliminada exitosamente"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting exception: {str(e)}", exc_info=True)
        if conn and mariadb_success:
            conn.rollback()
        if conn:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la excepción"
        )
