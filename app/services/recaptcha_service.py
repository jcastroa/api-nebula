# ==========================================
# app/services/recaptcha_service.py - Verificación reCAPTCHA
# ==========================================

"""Servicio para verificar Google reCAPTCHA"""
import httpx
from typing import Any, Dict, Optional
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class RecaptchaService:
    """Servicio para validar reCAPTCHA de Google"""
    
    def __init__(self):
        self.secret_key = settings.RECAPTCHA_SECRET_KEY
        self.verify_url = "https://www.google.com/recaptcha/api/siteverify"
        self.timeout = 10.0  # seconds
    
    async def verify_token(
        self, 
        token: str, 
        ip_address: str,
        min_score: float = 0.5
    ) -> bool:
        """
        Verificar token de reCAPTCHA con Google API
        
        Args:
            token: Token de reCAPTCHA del frontend
            ip_address: IP del cliente
            min_score: Score mínimo para reCAPTCHA v3 (0.0-1.0)
            
        Returns:
            True si la verificación es exitosa
        """
        if not self.is_enabled():
            logger.warning("reCAPTCHA verification called but service is disabled")
            return True
        
        if not token or len(token.strip()) == 0:
            logger.warning("Empty reCAPTCHA token provided")
            return False
        
        try:
            # Preparar datos para la API
            data = {
                'secret': self.secret_key,
                'response': token.strip(),
                'remoteip': ip_address
            }
            
            # Realizar request a Google API
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.verify_url, data=data)
                
                if response.status_code != 200:
                    logger.error(f"reCAPTCHA API returned status {response.status_code}")
                    return False
                
                result = response.json()
                
                # Verificar respuesta básica
                success = result.get('success', False)
                
                if not success:
                    error_codes = result.get('error-codes', [])
                    logger.warning(f"reCAPTCHA verification failed: {error_codes}")
                    
                    # Algunos errores específicos
                    if 'timeout-or-duplicate' in error_codes:
                        logger.warning("reCAPTCHA token already used or expired")
                    elif 'invalid-input-response' in error_codes:
                        logger.warning("Invalid reCAPTCHA token format")
                    
                    return False
                
                # reCAPTCHA v3 - verificar score si está disponible
                score = result.get('score')
                if score is not None:
                    logger.debug(f"reCAPTCHA score: {score}")
                    
                    if score < min_score:
                        logger.warning(f"reCAPTCHA score {score} below minimum {min_score}")
                        return False
                
                # Verificar acción si está disponible (reCAPTCHA v3)
                action = result.get('action')
                if action:
                    logger.debug(f"reCAPTCHA action: {action}")
                
                # Verificar hostname si está disponible
                hostname = result.get('hostname')
                if hostname:
                    logger.debug(f"reCAPTCHA hostname: {hostname}")
                
                logger.info(f"reCAPTCHA verification successful for IP {ip_address}")
                return True
                
        except httpx.TimeoutException:
            logger.error("reCAPTCHA verification timeout")
            return False
        except httpx.RequestError as e:
            logger.error(f"reCAPTCHA verification network error: {e}")
            return False
        except ValueError as e:
            logger.error(f"reCAPTCHA verification JSON parse error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected reCAPTCHA verification error: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """
        Verificar si reCAPTCHA está habilitado y configurado
        
        Returns:
            True si está habilitado y configurado correctamente
        """
        return (
            bool(self.secret_key) and 
            self.secret_key.strip() != "" and
            self.secret_key != "TU_CLAVE_RECAPTCHA" and
            len(self.secret_key) > 10  # Las claves de Google son largas
        )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Obtener status del servicio reCAPTCHA
        
        Returns:
            Dict con información del estado del servicio
        """
        return {
            "enabled": self.is_enabled(),
            "secret_key_configured": bool(self.secret_key and len(self.secret_key) > 5),
            "api_url": self.verify_url,
            "timeout": self.timeout
        }