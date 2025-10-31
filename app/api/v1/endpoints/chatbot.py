"""
Chatbot configuration endpoints.
Implements GET and POST operations for chatbot configuration management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any
from app.schemas.chatbot import (
    ChatbotConfiguracionRequest,
    ChatbotConfiguracionResponse,
    ChatbotConfiguracionSaveResponse,
    ConfiguracionEstructurada
)
from app.services.chatbot_service import ChatbotConfiguracionService
from app.services.firestore_service import FirestoreService 
from app.dependencies import get_current_user, get_firestore_service
import logging
from datetime import datetime


router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger(__name__)

def get_chatbot_service(
    firestore_service: FirestoreService = Depends(get_firestore_service)
) -> ChatbotConfiguracionService:
    """Dependency to get chatbot configuration service"""
    return ChatbotConfiguracionService(firestore_service)


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
    "/configuracion",
    response_model=ChatbotConfiguracionResponse,
    summary="Obtener configuración del chatbot",
    description="Obtiene la configuración actual del chatbot para el consultorio del usuario autenticado."
)
async def obtener_configuracion(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    chatbot_service: ChatbotConfiguracionService = Depends(get_chatbot_service)
):
    """
    Get chatbot configuration from MariaDB only.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 200: Configuration found and returned
    - 404: No configuration found for this consultorio
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"GET /chatbot/configuracion - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Get configuration from MariaDB
        config = await chatbot_service.get_configuracion_from_mariadb(negocio_id)

        if not config:
            logger.warning(f"No configuration found for negocio_id {negocio_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró configuración para este consultorio"
            )

        # Return configuration
        return ChatbotConfiguracionResponse(
            id=config['id'],
            negocio_id=config['negocio_id'],
            configuracion=config['configuracion'],
            prompt_completo=config['prompt_completo'],
            created_at=config['created_at'],
            updated_at=config['updated_at']
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except ValueError as e:
        # JSON parsing errors or validation errors
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    except Exception as e:
        # Unexpected errors
        logger.error(f"Error getting chatbot configuration: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la configuración del chatbot"
        )


@router.post(
    "/configuracion",
    response_model=ChatbotConfiguracionSaveResponse,
    status_code=status.HTTP_200_OK,
    summary="Guardar configuración del chatbot",
    description=(
        "Guarda o actualiza la configuración del chatbot para el consultorio del usuario autenticado. "
        "Implementa estrategia híbrida: persiste en MariaDB (configuración completa) y "
        "Firestore (prompt optimizado para el chatbot). Usa transacciones para garantizar consistencia."
    )
)
async def guardar_configuracion(
    payload: ChatbotConfiguracionRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    chatbot_service: ChatbotConfiguracionService = Depends(get_chatbot_service)
):
    """
    Save or update chatbot configuration to both MariaDB and Firestore using transactions.

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Request Body**:
    - `configuracion`: Structured chatbot configuration (business, services, policies, FAQs)
    - `prompt_completo`: Complete prompt generated by frontend (min 100 characters)

    **Response**:
    - 200: Configuration saved successfully
    - 400: Invalid request payload
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 422: Validation error
    - 500: Internal server error (transaction rolled back)

    **Transaction Behavior**:
    - Saves to MariaDB first (within transaction)
    - Then saves to Firestore
    - If Firestore fails, MariaDB is rolled back
    - Returns error 500 if either operation fails
    """
    try:
        # Get negocio_id from current user
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"POST /chatbot/configuracion - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # Validate payload (Pydantic already validated structure)
        # Additional validation can be added here if needed

        # Save with transaction (MariaDB + Firestore)
        result = await chatbot_service.save_configuracion_with_transaction(
            negocio_id=negocio_id,
            configuracion=payload.configuracion.model_dump(),
            prompt_completo=payload.prompt_completo
        )

        logger.info(
            f"Configuration saved successfully for negocio_id {negocio_id}, "
            f"config_id: {result['id']}"
        )

        # Return success response
        return ChatbotConfiguracionSaveResponse(
            success=True,
            message="Configuración guardada exitosamente",
            data={
                "id": result['id'],
                "negocio_id": result['negocio_id'],
                "updated_at": result['updated_at']
            }
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except ValueError as e:
        # Validation errors
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    except Exception as e:
        # Database transaction errors or Firestore errors
        logger.error(f"Error saving chatbot configuration: {str(e)}", exc_info=True)

        # Check if error message indicates Firestore or MariaDB failure
        error_detail = str(e)
        if "Firestore" in error_detail or "Firebase" in error_detail:
            error_detail = (
                "Error al guardar en Firestore. La configuración no se ha guardado. "
                "Por favor, intente nuevamente."
            )
        elif "MariaDB" in error_detail or "MySQL" in error_detail:
            error_detail = (
                "Error al guardar en la base de datos. "
                "Por favor, intente nuevamente."
            )
        else:
            error_detail = "Error al guardar la configuración del chatbot"

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )


@router.delete(
    "/configuracion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar configuración del chatbot",
    description="Elimina la configuración del chatbot del consultorio del usuario autenticado."
)
async def eliminar_configuracion(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    chatbot_service: ChatbotConfiguracionService = Depends(get_chatbot_service)
):
    """
    Delete chatbot configuration (optional endpoint for future use).

    **Authentication required**: Yes (HttpOnly cookies or Bearer token)

    **Response**:
    - 204: Configuration deleted successfully
    - 404: Configuration not found
    - 401: Authentication required
    - 403: User has no associated consultorio
    - 500: Internal server error
    """
    try:
        negocio_id = get_negocio_id_from_user(current_user)

        logger.info(
            f"DELETE /chatbot/configuracion - User: {current_user.get('id')}, "
            f"Negocio: {negocio_id}, IP: {request.client.host}"
        )

        # For now, just delete from MariaDB
        # Future: Also delete from Firestore if needed
        from app.crud.chatbot_configuracion import get_chatbot_configuracion_crud

        crud = get_chatbot_configuracion_crud()
        deleted = await crud.delete_by_negocio_id(negocio_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró configuración para eliminar"
            )

        logger.info(f"Configuration deleted for negocio_id {negocio_id}")
        return None

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting chatbot configuration: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la configuración del chatbot"
        )
