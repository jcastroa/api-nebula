# ==========================================
# app/api/v1/endpoints/auth.py - Endpoints de autenticación
# ==========================================

"""Endpoints de autenticación con cookies HttpOnly"""
from typing import Dict
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from datetime import datetime
import logging

from app.schemas.auth import (
    LoginRequest, 
    TokenResponse, 
    RefreshResponse, 
    LogoutResponse,
    CambiarConsultorioRequest
)
from app.schemas.user import UserResponse
from app.schemas.auth import UserCompleteInfo
from app.services.auth_service import AuthService
from app.dependencies import get_auth_service, get_current_user
from app.core.exceptions import (
    InvalidCredentialsException,
    RecaptchaException,
    SessionExpiredException,
    TokenExpiredException,
    TokenRevokedException
)
from app.core.security import generate_csrf_token, verify_token
from app.config import settings
from app.utils.schemas_converter import dict_to_user_complete_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")

@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    req: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Endpoint de login con autenticación completa
    - Verifica reCAPTCHA
    - Autentica usuario
    - Crea sesión con cookies HttpOnly
    - Genera CSRF token
    """
    
    client_ip = req.client.host
    user_agent = req.headers.get("user-agent", "Unknown")
    
    try:
        logger.info(f"Login attempt for user: {request.username} from IP: {client_ip}")
        
        # 1. Verificar reCAPTCHA si está habilitado
        # recaptcha_valid = await auth_service.verify_recaptcha(
        #     request.recaptcha_token, 
        #     client_ip
        # )
        
        # if not recaptcha_valid:
        #     logger.warning(f"reCAPTCHA verification failed for {request.username}")
        #     raise RecaptchaException()
        
        # 2. Autenticar usuario
        user = await auth_service.authenticate_user(
            request.username, 
            request.password
        )
        
        if not user:
            logger.warning(f"Authentication failed for user: {request.username}")
            raise InvalidCredentialsException()
        
        
        
        # 3. Crear sesión completa con tokens
        session = await auth_service.create_session(
            user['id'],
            request.device_info,
            client_ip,
            user_agent
        )

        # 2. Obtener Datos completos del usuario (roles y consultorios) validar si consultrio  ultimo activo es vacio manda none sino mandar ese id
        if user['ultimo_consultorio_activo'] is None :
            user_complete_info = await auth_service.obtener_datos_completos_usuario(
                user['id'],
                None
            )
        else:
             user_complete_info = await auth_service.obtener_datos_completos_usuario(
                user['id'],
                user['ultimo_consultorio_activo']
            )
       
     
        # 4. Configurar cookies HttpOnly para AMBOS tokens (MÁXIMA SEGURIDAD)
        
        # Access Token Cookie
        response.set_cookie(
            key="access_token",
            value=session["access_token"],
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 30 minutos
            httponly=True,      # No accesible desde JavaScript
            secure=not settings.DEBUG,  # HTTPS en producción
            samesite="lax",     # Protección CSRF
            path="/"            # Disponible en toda la app
        )
        
        # Refresh Token Cookie
        response.set_cookie(
            key="refresh_token",
            value=session["refresh_token"],
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 días
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            path="/api/v1/auth"  # Solo para endpoints de auth
        )
        
        # 5. CSRF Token (para formularios)
        csrf_token = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=False,     # JavaScript necesita leerlo para enviarlo
            secure=not settings.DEBUG,
            samesite="lax"
        )
        
        # 6. Preparar información del usuario para respuesta
        user_complete_info = dict_to_user_complete_info(user_complete_info)
        
        logger.info(f"User {user['username']} logged in successfully from {client_ip}")
        
        return TokenResponse(
            message="Login successful",
            user=user_complete_info,
            expires_in=session["expires_in"],
            session_id=session["session_id"],
            csrf_token=csrf_token
        )
        
    except (RecaptchaException, InvalidCredentialsException) as e:
        # Incrementar métrica de fallos
        from app.core.redis_client import redis_client
        redis_client.increment("metric:login_failures", ttl=86400)
        raise e
    except Exception as e:
        logger.error(f"Login error for {request.username}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(
    req: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Endpoint de refresh con rotación completa de tokens
    - Lee refresh token desde cookie HttpOnly
    - Genera AMBOS tokens nuevos
    - Actualiza AMBAS cookies
    """

    # Leer refresh token desde cookie
    refresh_token = req.cookies.get("refresh_token")
    if not refresh_token:
        logger.warning("Refresh attempt without refresh token cookie")
        raise HTTPException(status_code=401, detail="Refresh token required")
    
    try:
       
        
        logger.debug("Processing refresh token request")
        
        # Renovar sesión (rotación completa)
        new_tokens = await auth_service.refresh_session(refresh_token)
        
        # Actualizar AMBAS cookies con tokens nuevos
        response.set_cookie(
            key="access_token",
            value=new_tokens["access_token"],
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            path="/"
        )
        
        response.set_cookie(
            key="refresh_token",
            value=new_tokens["refresh_token"],
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            path="/api/v1/auth"
        )
        
        # Nuevo CSRF token
        csrf_token = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=False,
            secure=not settings.DEBUG,
            samesite="lax"
        )
        
        logger.info("Tokens refreshed successfully")
        
        return RefreshResponse(
            message="Tokens refreshed successfully",
            expires_in=new_tokens["expires_in"],
            csrf_token=csrf_token
        )
        
    except SessionExpiredException as e:
        # Sesión expirada por inactividad - limpiar cookies
        logger.info("Session expired due to inactivity - clearing cookies")
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        response.delete_cookie("csrf_token")
        raise e
    except (TokenExpiredException, TokenRevokedException) as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        logger.error(f"Refresh error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout", response_model=LogoutResponse)
async def logout(
    req: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout individual - revoca sesión actual
    """
    
    try:
        # Obtener session_id del token actual
        access_token = req.cookies.get("access_token")
        session_id = None
        
        if access_token:
            try:
                payload = verify_token(access_token)
                session_id = payload.get("session_id")
            except Exception:
                pass  # Token puede estar expirado
        
        # Revocar sesión si se encontró
        if session_id:
            await auth_service.revoke_session(session_id, "user_logout")
        
        # Limpiar TODAS las cookies
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        response.delete_cookie("csrf_token")
        
        logger.info(f"User {current_user['username']} logged out successfully")
        
        return LogoutResponse(
            message="Logged out successfully",
            logged_out_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Limpiar cookies de todas formas por seguridad
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/api/v1/auth")
        response.delete_cookie("csrf_token")
        
        return LogoutResponse(
            message="Logged out",
            logged_out_at=datetime.utcnow()
        )

@router.post("/logout-all")
async def logout_all_sessions(
    req: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout masivo - cierra todas las sesiones del usuario
    """
    
    try:
        # Obtener session_id actual para mantenerla (opcional)
        access_token = req.cookies.get("access_token")
        current_session_id = None
        
        if access_token:
            try:
                payload = verify_token(access_token)
                current_session_id = payload.get("session_id")
            except Exception:
                pass
        
        # Revocar todas las sesiones (manteniendo la actual)
        revoked_count = await auth_service.revoke_all_user_sessions(
            current_user['id'],
            "user_logout_all",
            exclude_session=current_session_id
        )
        
        logger.info(f"User {current_user['username']} logged out from {revoked_count} other sessions")
        
        return {
            "message": f"Logged out from {revoked_count} other sessions",
            "revoked_sessions": revoked_count,
            "current_session_maintained": True
        }
        
    except Exception as e:
        logger.error(f"Logout all error: {e}")
        raise HTTPException(status_code=500, detail="Error logging out from other sessions")

@router.get("/me", response_model=UserCompleteInfo)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Obtener información del usuario autenticado
    """

    if current_user['ultimo_consultorio_activo'] is None :
            user_complete_info = await auth_service.obtener_datos_completos_usuario(
                current_user['id'],
                None
            )
    else:
            user_complete_info = await auth_service.obtener_datos_completos_usuario(
            current_user['id'],
            current_user['ultimo_consultorio_activo']
        )

    return UserCompleteInfo(**user_complete_info)

@router.get("/sessions")
async def get_my_sessions(
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Obtener sesiones activas del usuario actual
    """
    try:
        sessions = await auth_service.get_user_sessions(
            current_user['id'],
            include_inactive=False
        )
        
        # Ocultar información sensible
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
        
        return {
            "sessions": safe_sessions,
            "total": len(safe_sessions)
        }
        
    except Exception as e:
        logger.error(f"Error getting sessions for user {current_user['id']}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching sessions")

@router.post("/sessions/{session_id}/revoke")
async def revoke_my_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revocar una sesión específica propia
    """
    try:
        # Verificar que la sesión pertenece al usuario
        user_sessions = await auth_service.get_user_sessions(current_user['id'])
        session_found = any(s['session_id'] == session_id for s in user_sessions)
        
        if not session_found:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Revocar la sesión
        success = await auth_service.revoke_session(session_id, "user_revoked")
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to revoke session")
        
        logger.info(f"User {current_user['username']} revoked session {session_id}")
        
        return {"message": "Session revoked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Error revoking session")
    
@router.post("/cambiar-consultorio")
async def cambiar_consultorio(
    consultorio_data: CambiarConsultorioRequest,  # Schema con consultorio_id
    current_user: Dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        # Obtener datos completos del usuario
        user_complete_info = await auth_service.obtener_datos_completos_usuario(
            current_user['id'],
            None
        )
       
        
        # Cambiar consultorio y obtener datos actualizados
        updated_data = await auth_service.cambiar_consultorio(
            current_user['id'],
            consultorio_data.consultorio_id,
            user_complete_info
        )
        
        # Convertir a schema
        user_complete_info = dict_to_user_complete_info(updated_data)
        
        return {
            "success": True,
            "message": "Consultorio cambiado exitosamente",
            "user": user_complete_info
        }
        
    except InvalidCredentialsException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error changing consultorio: {e}")
        raise HTTPException(status_code=500, detail="Error changing consultorio")