# ==========================================
# app/services/auth_service.py - Servicio principal de autenticación
# ==========================================

"""Servicio de autenticación - Lógica de negocio principal"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from app.crud.user import UserCRUD
from app.crud.session import SessionCRUD
from app.core.security import (
    verify_password, 
    create_access_token, 
    create_refresh_token,
    generate_session_id,
    generate_jti,
    verify_token
)
from app.core.redis_client import redis_client
from app.core.exceptions import (
    InvalidCredentialsException,
    TokenExpiredException,
    TokenRevokedException,
    SessionExpiredException,
    UserNotFoundException
)
from app.services.recaptcha_service import RecaptchaService
from app.config import settings

logger = logging.getLogger(__name__)

class AuthService:
    """Servicio principal de autenticación y gestión de sesiones"""
    
    def __init__(self):
        self.user_crud = UserCRUD()
        self.session_crud = SessionCRUD()
        self.recaptcha_service = RecaptchaService()
    
    async def authenticate_user(
        self, 
        username: str, 
        password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Autenticar usuario con credenciales
        
        Args:
            username: Nombre de usuario
            password: Contraseña en texto plano
            
        Returns:
            Dict con datos del usuario (sin password) o None si falla
        """
        try:
            # Obtener usuario con hash de password
            user = await self.user_crud.get_by_username(username)
            if not user:
                logger.warning(f"Login attempt with non-existent username: {username}")
                return None
            
            # Verificar contraseña
            if not verify_password(password, user['password_hash']):
                logger.warning(f"Invalid password attempt for user: {username}")
                return None
            
            # Verificar que esté activo
            if not user.get('is_active', True):
                logger.warning(f"Login attempt for inactive user: {username}")
                return None
            
            # Remover password_hash de la respuesta
            user.pop('password_hash', None)
            
            logger.info(f"User {username} authenticated successfully")
            return user
            
        except Exception as e:
            logger.error(f"Error authenticating user {username}: {e}")
            return None
        
    async def obtener_datos_completos_usuario(
        self, 
        usuario_id: int, 
        consultorio_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtener datos completos del usuario usando CRUD
        
        Args:
            usuario_id: ID del usuario
            consultorio_id: ID del consultorio específico (opcional)
            
        Returns:
            Dict con toda la información del usuario
        """
        try:
            # Usar método del CRUD para obtener datos completos
            user_data = await self.user_crud.get_complete_user_data(usuario_id, consultorio_id)
            
            if not user_data:
                raise UserNotFoundException(f"Usuario {usuario_id} no encontrado")
            
            logger.info(f"Loaded complete user data for user {usuario_id}")
            return user_data
            
        except Exception as e:
            logger.error(f"Error obtaining complete user data for {usuario_id}: {e}")
            raise
    
    async def cambiar_consultorio(
        self, 
        usuario_id: int, 
        consultorio_id: int,
        user_data_actual: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cambiar consultorio activo del usuario
        
        Args:
            usuario_id: ID del usuario
            consultorio_id: Nuevo consultorio activo
            user_data_actual: Datos actuales del usuario
            
        Returns:
            Dict con datos actualizados del usuario
        """
        try:
            # Verificar que el usuario tenga acceso al consultorio
            if not user_data_actual['es_superadmin']:
                consultorios_accesibles = [c['consultorio_id'] for c in user_data_actual['consultorios_usuario']]
                if consultorio_id not in consultorios_accesibles:
                    raise InvalidCredentialsException("Sin acceso a este consultorio")
            
            # Actualizar último consultorio activo usando CRUD
            updated = await self.user_crud.update_ultimo_consultorio_activo(usuario_id, consultorio_id)
            if not updated:
                raise Exception("Error updating ultimo_consultorio_activo")
            
            # Obtener datos actualizados con el nuevo contexto usando CRUD
            user_data = await self.user_crud.get_complete_user_data(usuario_id, consultorio_id)
            if not user_data:
                raise Exception("Error getting updated user data")
            
            logger.info(f"User {usuario_id} switched to consultorio {consultorio_id}")
            return user_data
            
        except Exception as e:
            logger.error(f"Error changing consultorio for user {usuario_id}: {e}")
            raise
        
    async def create_session(
        self, 
        user_id: int, 
        device_info: Dict[str, Any], 
        ip_address: str, 
        user_agent: str
    ) -> Dict[str, Any]:
        """
        Crear sesión completa con tokens y cache
        
        Args:
            user_id: ID del usuario
            device_info: Información del dispositivo
            ip_address: IP del cliente
            user_agent: User agent del browser
            
        Returns:
            Dict con tokens y datos de sesión
        """
        try:
            # Generar IDs únicos
            session_id = generate_session_id()
            access_jti = generate_jti()
            refresh_jti = generate_jti()
            
            logger.debug(f"Creating session for user {user_id}: {session_id}")
            
            # Crear payloads para tokens
            token_data = {
                "user_id": user_id,
                "session_id": session_id,
                "jti": access_jti
            }
            
            # Generar tokens JWT
            access_token = create_access_token(token_data.copy())
            
            token_data["jti"] = refresh_jti
            refresh_token = create_refresh_token(token_data.copy())
            
            # Calcular expiración
            expires_at = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
            
            # Guardar en Redis (cache para validaciones rápidas)
            session_cache_data = {
                "user_id": user_id,
                "last_activity": datetime.utcnow().isoformat(),
                "access_jti": access_jti,
                "refresh_jti": refresh_jti,
                "status": "active"
            }
            
            # Cache de sesión
            redis_client.set_json(
                f"session:{session_id}",
                session_cache_data,
                ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
            # Cache de actividad del usuario
            redis_client.set_json(
                f"user_activity:{user_id}",
                datetime.utcnow().isoformat(),
                ttl=settings.INACTIVITY_TIMEOUT_SECONDS
            )
            
            # Guardar en MySQL (persistencia para administración)
            session_record = {
                "user_id": user_id,
                "session_id": session_id,
                "access_token_jti": access_jti,
                "refresh_token_jti": refresh_jti,
                "device_info": device_info,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "expires_at": expires_at
            }
            
            await self.session_crud.create(session_record)
            
            # Incrementar métrica
            redis_client.increment("metric:sessions_created", ttl=86400)  # 24h
            
            logger.info(f"Session created successfully for user {user_id}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "session_id": session_id,
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
            
        except Exception as e:
            logger.error(f"Error creating session for user {user_id}: {e}")
            raise
    
    async def refresh_session(self, refresh_token: str) -> Dict[str, Any]:
        """
        Renovar sesión usando refresh token (con rotación completa)
        
        Args:
            refresh_token: Token de refresco actual
            
        Returns:
            Dict con nuevos tokens
        """
        try:
            # Verificar y decodificar refresh token
            payload = verify_token(refresh_token)
            
            if payload.get("type") != "refresh":
                logger.warning("Invalid token type for refresh")
                raise TokenExpiredException()
            
            user_id = payload["user_id"]
            session_id = payload["session_id"]
            refresh_jti = payload["jti"]
            
            logger.debug(f"Refreshing session {session_id} for user {user_id}")
            
            # Verificar que no esté en blacklist
            if redis_client.get_json(f"blacklist:{refresh_jti}"):
                logger.warning(f"Attempted to use blacklisted refresh token: {refresh_jti}")
                raise TokenRevokedException()
            
            # LAZY: Verificar inactividad solo cuando usuario intenta refresh
            if await self._is_user_inactive(user_id):
                logger.info(f"Revoking session {session_id} due to inactivity")
                await self.revoke_session(session_id, "inactivity_detected")
                raise SessionExpiredException()
            
            # INVALIDAR refresh token anterior INMEDIATAMENTE (rotación)
            redis_client.set_json(
                f"blacklist:{refresh_jti}",
                "refreshed",
                ttl=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            )
            
            # Generar NUEVOS tokens (AMBOS - access y refresh)
            new_access_jti = generate_jti()
            new_refresh_jti = generate_jti()
            
            new_token_data = {
                "user_id": user_id,
                "session_id": session_id,
                "jti": new_access_jti
            }
            
            new_access_token = create_access_token(new_token_data.copy())
            
            new_token_data["jti"] = new_refresh_jti
            new_refresh_token = create_refresh_token(new_token_data.copy())
            
            # Actualizar cache y base de datos
            await self._update_session_tokens(
                session_id, 
                user_id,
                new_access_jti, 
                new_refresh_jti
            )
            
            # Incrementar métrica
            redis_client.increment("metric:tokens_refreshed", ttl=86400)
            
            logger.info(f"Session refreshed successfully: {session_id}")
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
            
        except (TokenExpiredException, TokenRevokedException, SessionExpiredException):
            raise
        except Exception as e:
            logger.error(f"Error refreshing session: {e}")
            raise TokenExpiredException()
    
    async def revoke_session(
        self, 
        session_id: str, 
        reason: str = "user_logout"
    ) -> bool:
        """
        Revocar sesión específica
        
        Args:
            session_id: ID de la sesión a revocar
            reason: Motivo de la revocación
            
        Returns:
            True si se revocó exitosamente
        """
        try:
            # Obtener información de la sesión
            session = await self.session_crud.get(session_id)
            if not session:
                logger.warning(f"Attempted to revoke non-existent session: {session_id}")
                return False
            
            logger.info(f"Revoking session {session_id} for user {session['user_id']}: {reason}")
            
            # Blacklist tokens en Redis
            redis_client.set_json(
                f"blacklist:{session['access_token_jti']}",
                reason,
                ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
            redis_client.set_json(
                f"blacklist:{session['refresh_token_jti']}",
                reason,
                ttl=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            )
            
            # Limpiar cache de Redis
            redis_client.delete(f"session:{session_id}")
            redis_client.delete(f"user_activity:{session['user_id']}")
            
            # Actualizar estado en MySQL
            await self.session_crud.revoke_session(session_id, reason)
            
            # Incrementar métrica
            redis_client.increment("metric:sessions_revoked", ttl=86400)
            
            return True
            
        except Exception as e:
            logger.error(f"Error revoking session {session_id}: {e}")
            return False
    
    async def revoke_all_user_sessions(
        self, 
        user_id: int, 
        reason: str = "user_action",
        exclude_session: Optional[str] = None
    ) -> int:
        """
        Revocar todas las sesiones activas de un usuario
        
        Args:
            user_id: ID del usuario
            reason: Motivo de la revocación
            exclude_session: Sesión a excluir (mantener activa)
            
        Returns:
            Número de sesiones revocadas
        """
        try:
            logger.info(f"Revoking all sessions for user {user_id}: {reason}")
            
            # Obtener sesiones activas del usuario
            sessions = await self.session_crud.get_by_user(user_id, "active")
            
            revoked_count = 0
            for session in sessions:
                if exclude_session and session['session_id'] == exclude_session:
                    continue
                
                # Blacklist tokens en Redis
                redis_client.set_json(
                    f"blacklist:{session['access_token_jti']}",
                    reason,
                    ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                )
                
                redis_client.set_json(
                    f"blacklist:{session['refresh_token_jti']}",
                    reason,
                    ttl=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
                )
                
                # Limpiar cache de sesión
                redis_client.delete(f"session:{session['session_id']}")
                
                revoked_count += 1
            
            # Limpiar actividad del usuario
            redis_client.delete(f"user_activity:{user_id}")
            
            # Actualizar todas las sesiones en MySQL
            mysql_revoked = await self.session_crud.revoke_user_sessions(
                user_id, reason, exclude_session
            )
            
            # Incrementar métrica
            redis_client.increment("metric:bulk_sessions_revoked", ttl=86400)
            
            logger.info(f"Revoked {revoked_count} sessions for user {user_id}")
            return mysql_revoked
            
        except Exception as e:
            logger.error(f"Error revoking all sessions for user {user_id}: {e}")
            return 0
    
    async def verify_access_token(self, token: str) -> Dict[str, Any]:
        """
        Verificar access token y actualizar actividad
        
        Args:
            token: Access token a verificar
            
        Returns:
            Payload del token verificado
        """
        try:
            # Verificar y decodificar token JWT
            payload = verify_token(token)
            
            if payload.get("type") != "access":
                raise TokenExpiredException()
            
            access_jti = payload["jti"]
            user_id = payload["user_id"]
            session_id = payload["session_id"]
            
            # Verificar blacklist
            if redis_client.get_json(f"blacklist:{access_jti}"):
                logger.debug(f"Access token {access_jti} is blacklisted")
                raise TokenRevokedException()
            
            # Verificar sesión activa en cache
            session_data = redis_client.get_json(f"session:{session_id}")
            if not session_data:
                logger.debug(f"Session {session_id} not found in cache")
                raise SessionExpiredException()
            
            # Actualizar actividad del usuario
            await self._update_user_activity(user_id, session_id)
            
            return payload
            
        except (TokenExpiredException, TokenRevokedException, SessionExpiredException):
            raise
        except Exception as e:
            logger.error(f"Error verifying access token: {e}")
            raise TokenExpiredException()
    
    async def verify_recaptcha(self, token: str, ip_address: str) -> bool:
        """
        Verificar reCAPTCHA si está habilitado
        
        Args:
            token: Token de reCAPTCHA
            ip_address: IP del cliente
            
        Returns:
            True si es válido o está deshabilitado
        """
        if not self.recaptcha_service.is_enabled():
            logger.debug("reCAPTCHA verification skipped (disabled)")
            return True
        
        return await self.recaptcha_service.verify_token(token, ip_address)
    
    async def get_user_sessions(
        self, 
        user_id: int, 
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtener sesiones de un usuario
        
        Args:
            user_id: ID del usuario
            include_inactive: Incluir sesiones inactivas
            
        Returns:
            Lista de sesiones
        """
        try:
            if include_inactive:
                # Obtener todas las sesiones
                sessions = []
                for status in ['active', 'expired', 'revoked']:
                    user_sessions = await self.session_crud.get_by_user(user_id, status)
                    sessions.extend(user_sessions)
                return sorted(sessions, key=lambda x: x['created_at'], reverse=True)
            else:
                # Solo sesiones activas
                return await self.session_crud.get_by_user(user_id, "active")
        except Exception as e:
            logger.error(f"Error getting sessions for user {user_id}: {e}")
            return []
    
    
    # ==========================================
    # MÉTODOS PRIVADOS (HELPER METHODS)
    # ==========================================
    
    async def _is_user_inactive(self, user_id: int) -> bool:
        """
        Verificar si usuario está inactivo (> 1 hora sin actividad)
        
        Args:
            user_id: ID del usuario a verificar
            
        Returns:
            True si está inactivo
        """
        try:
            last_activity_str = redis_client.get_json(f"user_activity:{user_id}")
            if not last_activity_str:
                logger.debug(f"No activity found for user {user_id}")
                return True
            
            # Parsear fecha de actividad
            if isinstance(last_activity_str, str):
                last_time = datetime.fromisoformat(last_activity_str)
            else:
                last_time = datetime.fromisoformat(str(last_activity_str))
            
            # Calcular segundos inactivos
            inactive_seconds = (datetime.utcnow() - last_time).total_seconds()
            is_inactive = inactive_seconds > settings.INACTIVITY_TIMEOUT_SECONDS
            
            if is_inactive:
                logger.debug(f"User {user_id} inactive for {inactive_seconds} seconds")
            
            return is_inactive
            
        except Exception as e:
            logger.error(f"Error checking inactivity for user {user_id}: {e}")
            return True  # Asumir inactivo en caso de error por seguridad
    
    async def _update_user_activity(self, user_id: int, session_id: str):
        """
        Actualizar timestamp de actividad del usuario
        
        Args:
            user_id: ID del usuario
            session_id: ID de la sesión
        """
        try:
            now = datetime.utcnow()
            
            # Actualizar actividad en Redis
            redis_client.set_json(
                f"user_activity:{user_id}",
                now.isoformat(),
                ttl=settings.INACTIVITY_TIMEOUT_SECONDS
            )
            
            # Actualizar cache de sesión
            session_data = redis_client.get_json(f"session:{session_id}")
            if session_data:
                session_data["last_activity"] = now.isoformat()
                redis_client.set_json(
                    f"session:{session_id}",
                    session_data,
                    ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                )
            
            # Actualizar en MySQL (menos frecuente para performance)
            await self.session_crud.update_last_activity(session_id)
            
        except Exception as e:
            logger.error(f"Error updating activity for user {user_id}: {e}")
    
    async def _update_session_tokens(
        self, 
        session_id: str, 
        user_id: int,
        new_access_jti: str, 
        new_refresh_jti: str
    ):
        """
        Actualizar tokens de sesión en cache y base de datos
        
        Args:
            session_id: ID de la sesión
            user_id: ID del usuario  
            new_access_jti: Nuevo JTI del access token
            new_refresh_jti: Nuevo JTI del refresh token
        """
        try:
            now = datetime.utcnow()
            expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            
            # Actualizar cache de Redis
            session_data = {
                "user_id": user_id,
                "last_activity": now.isoformat(),
                "access_jti": new_access_jti,
                "refresh_jti": new_refresh_jti,
                "status": "active"
            }
            
            redis_client.set_json(
                f"session:{session_id}",
                session_data,
                ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
            # Actualizar actividad del usuario
            redis_client.set_json(
                f"user_activity:{user_id}",
                now.isoformat(),
                ttl=settings.INACTIVITY_TIMEOUT_SECONDS
            )
            
            # Actualizar en MySQL
            await self.session_crud.update(session_id, {
                "access_token_jti": new_access_jti,
                "refresh_token_jti": new_refresh_jti,
                "last_activity": now,
                "expires_at": expires_at
            })
            
        except Exception as e:
            logger.error(f"Error updating session tokens for {session_id}: {e}")
            raise