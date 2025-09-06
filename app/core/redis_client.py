"""Cliente Redis configurado"""
import redis
import json
from typing import Any, Optional, List
from app.config import settings
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
    
    def ping(self) -> bool:
        """Verificar conexión Redis"""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False
    
    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Guardar objeto JSON con TTL opcional"""
        try:
            json_value = json.dumps(value, default=str)
            if ttl:
                return self.client.setex(key, ttl, json_value)
            return self.client.set(key, json_value)
        except Exception as e:
            logger.error(f"Redis set_json error: {e}")
            return False
    
    def get_json(self, key: str) -> Optional[Any]:
        """Obtener objeto JSON"""
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get_json error: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Eliminar clave"""
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def increment(self, key: str, ttl: Optional[int] = None) -> int:
        """Incrementar contador con TTL"""
        try:
            value = self.client.incr(key)
            if ttl and value == 1:
                self.client.expire(key, ttl)
            return value
        except Exception as e:
            logger.error(f"Redis increment error: {e}")
            return 0
    
    # MÉTODOS NUEVOS QUE FALTAN:
    
    def scan_keys(self, pattern: str) -> List[str]:
        """Escanear claves que coincidan con un patrón"""
        try:
            keys = []
            for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"Redis scan_keys error with pattern {pattern}: {e}")
            return []
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Establecer valor con TTL opcional"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            
            if expire:
                return self.client.setex(key, expire, value)
            return self.client.set(key, value)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Obtener valor (con auto-parsing de JSON si es posible)"""
        try:
            value = self.client.get(key)
            if value is None:
                return None
            
            # Intentar parsear como JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Si no es JSON válido, devolver como string
                return value
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def exists(self, key: str) -> bool:
        """Verificar si existe una clave"""
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """Obtener TTL de una clave"""
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error: {e}")
            return -1
    
    def expire(self, key: str, seconds: int) -> bool:
        """Establecer TTL en una clave existente"""
        try:
            return self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False
    
    # MÉTODOS DE LIMPIEZA:
    
    def cleanup_expired_activities(self) -> int:
        """Limpiar actividades expiradas"""
        try:
            activity_keys = self.scan_keys("activity:*")
            cleaned = 0
            
            for key in activity_keys:
                ttl = self.ttl(key)
                if ttl == -2:  # Clave no existe
                    cleaned += 1
                elif ttl == -1:  # Sin TTL (huérfana)
                    # Eliminar actividades sin TTL que sean muy antiguas
                    try:
                        activity_data = self.get_json(key)
                        if activity_data and 'timestamp' in activity_data:
                            # Si es más antigua que 24 horas, eliminar
                            activity_time = datetime.fromisoformat(activity_data['timestamp'])
                            if datetime.utcnow() - activity_time > timedelta(hours=24):
                                self.delete(key)
                                cleaned += 1
                    except:
                        # Si no podemos parsear, eliminar por seguridad
                        self.delete(key)
                        cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} expired activity entries")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning Redis activities: {e}")
            return 0
    
    def cleanup_old_metrics(self, days: int = 7) -> int:
        """Limpiar métricas antiguas"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            metrics_keys = self.scan_keys("metrics:*")
            cleaned = 0
            
            for key in metrics_keys:
                try:
                    # Extraer fecha de la clave si tiene formato metrics:YYYY-MM-DD:*
                    parts = key.split(":")
                    if len(parts) >= 2:
                        date_part = parts[1]
                        # Verificar si es una fecha válida y antigua
                        if len(date_part) == 10 and date_part < cutoff_str:
                            self.delete(key)
                            cleaned += 1
                except (IndexError, ValueError):
                    # Si no podemos extraer fecha, verificar el contenido
                    try:
                        metric_data = self.get_json(key)
                        if metric_data and 'timestamp' in metric_data:
                            metric_time = datetime.fromisoformat(metric_data['timestamp'])
                            if metric_time < cutoff_date:
                                self.delete(key)
                                cleaned += 1
                    except:
                        continue
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} old metric entries")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning old metrics: {e}")
            return 0
    
    def cleanup_blacklist_orphans(self) -> int:
        """Limpiar tokens blacklist huérfanos (sin TTL)"""
        try:
            blacklist_keys = self.scan_keys("blacklist:*")
            cleaned = 0
            
            for key in blacklist_keys:
                ttl = self.ttl(key)
                if ttl == -1:  # Sin TTL (huérfano)
                    self.delete(key)
                    cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} orphaned blacklist entries")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning blacklist orphans: {e}")
            return 0
    
    # MÉTODO DE SALUD:
    
    def health_check(self) -> dict:
        """Verificar estado de Redis"""
        try:
            # Ping test
            ping_ok = self.ping()
            if not ping_ok:
                return {"status": "error", "error": "Ping failed"}
            
            # Obtener info del servidor
            info = self.client.info()
            
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "keyspace": info.get("db0", {}),
                "ping": ping_ok
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

# Instancia global
redis_client = RedisClient()