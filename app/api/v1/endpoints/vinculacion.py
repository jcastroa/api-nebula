"""Endpoints para gestión de usuarios"""
from datetime import datetime
import json
import uuid
from app.services.auth_service import AuthService
from fastapi import APIRouter, Depends, HTTPException, Query

import logging
import requests

from app.schemas.vinculacion import (
    CompletarVinculacionRequest
)
from app.schemas.response import SuccessResponse
from app.dependencies import get_auth_service, get_current_user, get_user_crud

from urllib.parse import urlencode, quote


from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vinculacion")

# Almacenamiento temporal (en producción usar Redis)
oauth_sessions = {}

# ========================================
# PASO 1: INICIAR VINCULACIÓN
# ========================================

@router.post("/paso1-iniciar")
async def paso1_iniciar_vinculacion(current_user: dict = Depends(get_current_user),
                                    auth_service: AuthService = Depends(get_auth_service)):
    """
    PASO 1: Usuario hace clic en "Conectar con Meta"
    
    Genera la URL de OAuth para que el usuario autorice.
    """
    
    session_id = str(uuid.uuid4())

    logger.info(f"Datos en current_user: {current_user}")

    redirect_uri = f"{settings.REDIRECT_BASE_URI}/configuracion/whatsapp-callback"

    # user_complete_info = await auth_service.obtener_datos_completos_usuario(
    #         current_user['id'],
    #         None
    #     )
    
    #logger.info(f"Datos completos usuario: {user_complete_info}")
    
    oauth_sessions[session_id] = {
        "negocio": current_user['ultimo_consultorio_activo'],
        "webhook_url": settings.WEBHOOK_BASE_URI,
        "webhook_token": None,
        "redirect_url": settings.REDIRECT_BASE_URI + "/configuracion/whatsapp-callback",
        "created_at": datetime.now().isoformat(),
        "step": "1_oauth_pending"
    }
    
    state = f"session_{session_id}"
    
    # ✅ OPCIÓN 2: Construir con urllib (más limpio)
    #extras_config = {"setup": {"channel": "whatsapp"}}
    
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "business_management,whatsapp_business_management,whatsapp_business_messaging",
        "response_type": "code",
        "config_id": "1212639360701117",
        "override_default_response_type": "true",
    }
    
    oauth_url = f"https://www.facebook.com/{settings.META_API_VERSION}/dialog/oauth?{urlencode(params)}"

    logger.info(f"[Vinculacion] Iniciado paso 1 para usuario {current_user['id']}, sesión {session_id}, oauth_session: {oauth_sessions[session_id]}")
    
    return {
        "success": True,
        "paso": 1,
        "session_id": session_id,
        "oauth_url": oauth_url,
        "mensaje": "Redirige al usuario a oauth_url para autorizar en Facebook",
        "prueba" : oauth_sessions[session_id]
    }


# ========================================
# PASO 2: OBTENER NÚMEROS DISPONIBLES
# ========================================

@router.post("/paso2-obtener-numeros")
async def paso2_obtener_numeros(request: CompletarVinculacionRequest):
    """
    PASO 2: Después del OAuth, obtiene los números disponibles.
    """
    logger.info(f"[Vinculacion][Paso2] Inicio. session_id={request.session_id}")

    if request.session_id not in oauth_sessions:
        logger.warning(f"[Vinculacion][Paso2] Sesión no encontrada: {request.session_id}")
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    session_data = oauth_sessions[request.session_id]
    logger.debug(f"[Vinculacion][Paso2] session_data antes intercambio: {session_data}")

    try:
        # Intercambiar code por access_token
        token_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/oauth/access_token"
        token_params = {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "code": request.code,
            "redirect_uri": session_data["redirect_url"]
        }

        logger.info(f"[Vinculacion][Paso2] Solicitando access token a Meta")
        token_response = requests.get(token_url, params=token_params, timeout=15)
        logger.info(f"[Vinculacion][Paso2] token_response.status_code={token_response.status_code}")
        token_response.raise_for_status()

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            logger.error(f"[Vinculacion][Paso2] No se recibió access_token")
            raise HTTPException(status_code=500, detail="No se recibió access_token desde Meta")

        logger.info(f"[Vinculacion][Paso2] Access token recibido (length={len(access_token)})")

        # Obtener user ID
        me_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/me"
        logger.info(f"[Vinculacion][Paso2] Solicitando /me a Meta")
        me_response = requests.get(me_url, params={"access_token": access_token}, timeout=15)
        me_response.raise_for_status()
        user_data = me_response.json()
        user_id = user_data['id']
        logger.debug(f"[Vinculacion][Paso2] user_id: {user_id}")

        # ✅ CAMBIO 1: Obtener Business Managers del usuario
        businesses_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{user_id}/businesses"
        businesses_params = {
            "access_token": access_token,
            "fields": "id,name"
        }
        logger.info(f"[Vinculacion][Paso2] Obteniendo Business Managers")
        businesses_response = requests.get(businesses_url, params=businesses_params, timeout=15)
        businesses_response.raise_for_status()
        businesses_data = businesses_response.json()
        
        if not businesses_data.get("data"):
            logger.warning(f"[Vinculacion][Paso2] Usuario sin Business Managers")
            raise HTTPException(
                status_code=400,
                detail="No tienes Business Managers configurados. Configura uno en business.facebook.com"
            )
        
        business_id = businesses_data["data"][0]["id"]
        business_name = businesses_data["data"][0].get("name", "Sin nombre")
        logger.info(f"[Vinculacion][Paso2] Business encontrado: id={business_id}, name={business_name}")

        # ✅ CAMBIO 2: Obtener WABA desde el Business Manager
        waba_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{business_id}/owned_whatsapp_business_accounts"
        waba_params = {
            "access_token": access_token,
            "fields": "id,name,account_review_status"
        }
        logger.info(f"[Vinculacion][Paso2] Obteniendo WABA del business {business_id}")
        waba_response = requests.get(waba_url, params=waba_params, timeout=15)
        waba_response.raise_for_status()
        waba_data = waba_response.json()
        
        if not waba_data.get("data"):
            logger.warning(f"[Vinculacion][Paso2] Business sin WABA configurada")
            raise HTTPException(
                status_code=400,
                detail="No tienes WhatsApp Business Accounts configuradas en tu Business Manager"
            )

        waba = waba_data["data"][0]
        waba_id = waba["id"]
        waba_name = waba.get("name", "WhatsApp Business")
        logger.info(f"[Vinculacion][Paso2] WABA encontrada: id={waba_id}, name={waba_name}")

        # ✅ CAMBIO 3: Obtener números (este ya estaba correcto)
        phones_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{waba_id}/phone_numbers"
        phones_params = {
            "access_token": access_token,
            "fields": "id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier"
        }
        logger.info(f"[Vinculacion][Paso2] Obteniendo números del WABA {waba_id}")
        phones_response = requests.get(phones_url, params=phones_params, timeout=15)
        phones_response.raise_for_status()
        phones_data = phones_response.json()

        if not phones_data.get("data"):
            logger.warning(f"[Vinculacion][Paso2] No hay números en WABA id={waba_id}")
            raise HTTPException(
                status_code=400,
                detail="No hay números de teléfono registrados en tu WhatsApp Business Account"
            )

        # Formatear números
        numeros_disponibles = []
        for phone in phones_data["data"]:
            numeros_disponibles.append({
                "phone_number_id": phone.get("id"),
                "display_phone_number": phone.get("display_phone_number"),
                "verified_name": phone.get("verified_name", "Sin nombre"),
                "quality_rating": phone.get("quality_rating", "N/A"),
                "code_verification_status": phone.get("code_verification_status", "N/A"),
                "messaging_limit_tier": phone.get("messaging_limit_tier", "N/A")
            })
        
        logger.info(f"[Vinculacion][Paso2] {len(numeros_disponibles)} números encontrados")

        # Guardar en sesión
        session_data.update({
            "access_token": access_token,
            "user_id": user_id,
            "business_id": business_id,
            "business_name": business_name,
            "waba_id": waba_id,
            "waba_name": waba_name,
            "numeros_disponibles": numeros_disponibles,
            "step": "2_waiting_selection"
        })
        oauth_sessions[request.session_id] = session_data

        return {
            "success": True,
            "paso": 2,
            "session_id": request.session_id,
            "business_name": business_name,
            "waba_name": waba_name,
            "total_numeros": len(numeros_disponibles),
            "numeros_disponibles": numeros_disponibles,
            "mensaje": "Selecciona un número de teléfono para continuar"
        }

    # ✅ IMPORTANTE: Captura HTTPException primero y NO la modifiques
    except HTTPException:
        # Marcar sesión como fallida pero RE-LANZAR la excepción original
        session_data["step"] = "failed"
        oauth_sessions[request.session_id] = session_data
        raise  # ← Re-lanza la HTTPException original sin modificarla
        
    except requests.exceptions.HTTPError as e:
        # Errores HTTP de requests (Meta API)
        error_detail = e.response.json() if e.response.content else {}
        logger.exception(f"[Vinculacion][Paso2] Error HTTP de Meta API: {error_detail}")
        session_data["step"] = "failed"
        oauth_sessions[request.session_id] = session_data
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error de Meta API: {error_detail.get('error', {}).get('message', str(e))}"
        )
        
    except requests.exceptions.RequestException as e:
        # Errores de conexión
        logger.exception(f"[Vinculacion][Paso2] Error de conexión con Meta API")
        session_data["step"] = "failed"
        oauth_sessions[request.session_id] = session_data
        raise HTTPException(status_code=500, detail=f"Error de conexión con Meta: {str(e)}")
        
    except Exception as e:
        # Otros errores no previstos
        logger.exception(f"[Vinculacion][Paso2] Error inesperado: {type(e).__name__}")
        session_data["step"] = "failed"
        oauth_sessions[request.session_id] = session_data
        raise HTTPException(status_code=500, detail="Error interno del servidor")

    

    