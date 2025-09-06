# ==========================================
# app/workers/cleanup_worker.py - Worker de limpieza
# ==========================================

"""Worker para limpieza automática de sesiones inactivas"""
import asyncio
from datetime import datetime, timedelta
import logging

from app.core.redis_client import redis_client
from app.crud.session import SessionCRUD
from app.config import settings

logger = logging.getLogger(__name__)

class CleanupWorker:
    """
    Worker para limpieza automática de sesiones y datos temporales
    """
    
    def __init__(self):
        self.session_crud = SessionCRUD()
        self.retention_hours = getattr(settings, 'CLEANUP_RETENTION_HOURS', 6)
        self.running = False
    
    async def start(self):
        """Iniciar el worker de limpieza"""
        if self.running:
            logger.warning("Cleanup worker already running")
            return
        
        self.running = True
        logger.info("🧹 Starting cleanup worker")
        
        # Ejecutar limpieza inicial
        await self.cleanup_inactive_sessions()
        
        logger.info("✅ Cleanup worker started successfully")
    
    async def stop(self):
        """Detener el worker de limpieza"""
        self.running = False
        logger.info("🛑 Cleanup worker stopped")
    
    async def cleanup_inactive_sessions(self) -> dict:
        """
        Ejecutar limpieza completa de sesiones inactivas
        
        Returns:
            Dict con estadísticas de la limpieza
        """
        
        logger.info("🧹 Starting cleanup of inactive sessions")
        
        try:
            stats = {
                "start_time": datetime.utcnow().isoformat(),
                "redis_keys_cleaned": 0,
                "mysql_sessions_updated": 0,
                "errors": []
            }
            
            cutoff_time = datetime.utcnow() - timedelta(hours=self.retention_hours)
            
            # 1. Limpiar actividades de usuario viejas en Redis
            stats["redis_keys_cleaned"] = await self._cleanup_redis_activities(cutoff_time)
            
            # 2. Actualizar sesiones expiradas en MySQL
            stats["mysql_sessions_updated"] = await self._cleanup_mysql_sessions(cutoff_time)
            
            # 3. Limpiar métricas antiguas en Redis (opcional)
            await self._cleanup_old_metrics()
            
            stats["end_time"] = datetime.utcnow().isoformat()
            stats["duration_seconds"] = (
                datetime.fromisoformat(stats["end_time"]) - 
                datetime.fromisoformat(stats["start_time"])
            ).total_seconds()
            
            logger.info(
                f"✅ Cleanup completed: {stats['redis_keys_cleaned']} Redis keys, "
                f"{stats['mysql_sessions_updated']} MySQL sessions updated in "
                f"{stats['duration_seconds']:.2f}s"
            )
            
            # Guardar estadísticas en Redis para el panel admin
            redis_client.set_json(
                "cleanup:last_run", 
                stats, 
                ttl=7 * 24 * 60 * 60  # 7 días
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error in cleanup process: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _cleanup_redis_activities(self, cutoff_time: datetime) -> int:
        """Limpiar actividades de usuario viejas en Redis"""
        
        cleaned_count = 0
        
        try:
            # Buscar todas las claves de actividad de usuario
            activity_keys = redis_client.scan_keys("user_activity:*")
            
            for key in activity_keys:
                try:
                    last_activity_str = redis_client.get_json(key)
                    if not last_activity_str:
                        # Clave vacía o corrupta, eliminar
                        redis_client.delete(key)
                        cleaned_count += 1
                        continue
                    
                    # Parsear fecha de actividad
                    if isinstance(last_activity_str, str):
                        last_time = datetime.fromisoformat(last_activity_str)
                    else:
                        last_time = datetime.fromisoformat(str(last_activity_str))
                    
                    # Si es más antigua que el cutoff, eliminar
                    if last_time < cutoff_time:
                        user_id = key.split(":")[1]
                        
                        # Eliminar actividad del usuario
                        redis_client.delete(key)
                        
                        # También buscar y eliminar sesiones relacionadas
                        session_keys = redis_client.scan_keys(f"session:*")
                        for session_key in session_keys:
                            session_data = redis_client.get_json(session_key)
                            if session_data and session_data.get("user_id") == int(user_id):
                                redis_client.delete(session_key)
                        
                        cleaned_count += 1
                        logger.debug(f"Cleaned Redis data for inactive user {user_id}")
                
                except (ValueError, TypeError) as e:
                    # Formato de fecha inválido o datos corruptos
                    logger.warning(f"Invalid activity data in {key}, deleting: {e}")
                    redis_client.delete(key)
                    cleaned_count += 1
                
                except Exception as e:
                    logger.error(f"Error processing key {key}: {e}")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning Redis activities: {e}")
            return 0
    
    async def _cleanup_mysql_sessions(self, cutoff_time: datetime) -> int:
        """Marcar sesiones expiradas en MySQL"""
        
        try:
            updated_count = await self.session_crud.cleanup_expired_sessions(
                self.retention_hours
            )
            
            logger.debug(f"Updated {updated_count} expired sessions in MySQL")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error cleaning MySQL sessions: {e}")
            return 0
    
    async def _cleanup_old_metrics(self):
        """Limpiar métricas muy antiguas de Redis"""
        
        try:
            # Las métricas diarias tienen TTL automático de 24h
            # Solo limpiamos métricas huérfanas sin TTL
            metric_keys = redis_client.scan_keys("metric:*")
            
            for key in metric_keys:
                # Verificar si la métrica tiene TTL
                ttl = redis_client.client.ttl(key)
                if ttl == -1:  # No TTL configurado
                    # Configurar TTL de 24 horas para métricas huérfanas
                    redis_client.client.expire(key, 86400)
                    logger.debug(f"Set TTL for orphaned metric: {key}")
            
        except Exception as e:
            logger.error(f"Error cleaning old metrics: {e}")
    
    async def get_cleanup_stats(self) -> dict:
        """Obtener estadísticas de la última limpieza"""
        
        try:
            stats = redis_client.get_json("cleanup:last_run")
            if stats:
                return stats
            else:
                return {"message": "No cleanup has been run yet"}
        except Exception as e:
            logger.error(f"Error getting cleanup stats: {e}")
            return {"error": str(e)}