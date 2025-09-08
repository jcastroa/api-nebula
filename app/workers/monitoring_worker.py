# ==========================================
# app/workers/monitoring_worker.py - Worker de monitoreo Firestore
# ==========================================

"""Worker para monitorear cambios en Firestore y notificar via WebSocket"""
import asyncio
from typing import Dict, Set
import logging
from datetime import datetime

from app.services.firestore_service import FirestoreService
from app.core.redis_client import redis_client
from app.websocket.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class FirestoreMonitoringWorker:
    """
    Worker que monitorea cambios en Firestore cada 30 segundos
    y notifica a clientes via WebSocket cuando detecta diferencias
    """
    
    def __init__(self):
        self.firestore_service = FirestoreService()
        self.running = False
        self.check_interval = 30  # segundos
        self.redis_prefix = "firestore_count:"
        self.first_run = True
        
        # Set de negocios conocidos para detectar nuevos
        self.known_negocios: Set[str] = set()
    
    async def start(self):
        """Iniciar el worker de monitoreo"""
        if self.running:
            logger.warning("Monitoring worker already running")
            return
        
        self.running = True
        logger.info("🔍 Starting Firestore monitoring worker (30s interval)")
        
        while self.running:
            try:
                await self._monitor_cycle()
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in monitoring cycle: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info("🛑 Firestore monitoring worker stopped")
    
    def stop(self):
        """Detener el worker"""
        self.running = False
        logger.info("🛑 Stopping Firestore monitoring worker...")
    
    async def _monitor_cycle(self):
        """Ejecutar un ciclo de monitoreo"""
        try:
            logger.debug("🔍 Starting monitoring cycle...")
            
            # 1. Obtener conteos actuales de Firestore
            current_counts = await self.firestore_service.get_counts_for_all_negocios()
            
            if not current_counts:
                logger.warning("No se obtuvieron conteos de Firestore")
                return
            
            # 2. Comparar con conteos previos en Redis
            changes_detected = await self._detect_changes(current_counts)
            
            # 3. Actualizar conteos en Redis
            await self._update_redis_counts(current_counts)
            
            # 4. Notificar cambios via WebSocket (solo después del primer run)
            if not self.first_run and changes_detected:
                await self._notify_changes(changes_detected)
            
            # 5. Actualizar conocimiento de negocios
            self.known_negocios.update(current_counts.keys())
            
            # 6. Marcar que ya no es el primer run
            if self.first_run:
                self.first_run = False
                logger.info(f"📊 Initial monitoring setup completed. Watching {len(current_counts)} negocios")
            
            # 7. Guardar estadísticas
            await self._save_monitoring_stats(current_counts, changes_detected)
            
            logger.debug(f"✅ Monitoring cycle completed. Checked {len(current_counts)} negocios")
            
        except Exception as e:
            logger.error(f"❌ Error in monitoring cycle: {e}")
            raise
    
    async def _detect_changes(self, current_counts: Dict[str, int]) -> Dict[str, Dict]:
        """
        Detectar cambios comparando conteos actuales vs previos
        
        Args:
            current_counts: Conteos actuales desde Firestore
            
        Returns:
            Dict con cambios detectados por negocio
        """
        changes = {}
        
        for negocio, current_count in current_counts.items():
            # Obtener conteo previo de Redis
            redis_key = f"{self.redis_prefix}{negocio}"
            previous_count = redis_client.get_json(redis_key) or 0
            
            # Detectar cambio
            if current_count != previous_count:
                difference = current_count - previous_count
                
                changes[negocio] = {
                    "previous_count": previous_count,
                    "current_count": current_count,
                    "difference": difference,
                    "change_type": "increase" if difference > 0 else "decrease",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info(f"📊 Change detected in {negocio}: {previous_count} → {current_count} ({difference:+d})")
        
        # Detectar negocios nuevos
        for negocio in current_counts:
            if negocio not in self.known_negocios:
                logger.info(f"🆕 New negocio detected: {negocio}")
                if negocio not in changes:
                    changes[negocio] = {
                        "previous_count": 0,
                        "current_count": current_counts[negocio],
                        "difference": current_counts[negocio],
                        "change_type": "new_negocio",
                        "timestamp": datetime.utcnow().isoformat()
                    }
        
        return changes
    
    async def _update_redis_counts(self, current_counts: Dict[str, int]):
        """Actualizar conteos en Redis"""
        try:
            for negocio, count in current_counts.items():
                redis_key = f"{self.redis_prefix}{negocio}"
                
                # Guardar conteo con TTL de 1 hora (por si el worker se detiene)
                redis_client.set_json(redis_key, count, ttl=3600)
            
            # Guardar timestamp de última actualización
            redis_client.set_json(
                "firestore_monitoring:last_update",
                datetime.utcnow().isoformat(),
                ttl=3600
            )
            
        except Exception as e:
            logger.error(f"Error updating Redis counts: {e}")
    
    async def _notify_changes(self, changes: Dict[str, Dict]):
        """
        Notificar cambios via WebSocket a usuarios conectados
        
        Args:
            changes: Dict con cambios por negocio
        """
        notifications_sent = 0
        
        for negocio, change_data in changes.items():
            try:
                # Verificar si hay usuarios conectados para este negocio
                connected_users = websocket_manager.get_negocio_connections(negocio)
                
                if not connected_users:
                    logger.debug(f"No connected users for negocio {negocio}, skipping notification")
                    continue
                
                # Preparar mensaje de notificación
                notification_data = {
                    "message": f"Detected changes in {negocio}",
                    "change_summary": {
                        "count_changed": True,
                        "previous": change_data["previous_count"],
                        "current": change_data["current_count"],
                        "difference": change_data["difference"],
                        "type": change_data["change_type"]
                    },
                    "action_required": "refresh_data",
                    "refresh_endpoint": f"/api/v1/negocios/{negocio}/refresh"
                }
                
                # Notificar a todos los usuarios del negocio
                await websocket_manager.notify_negocio_changes(negocio, notification_data)
                notifications_sent += 1
                
                logger.info(f"📡 Notified {len(connected_users)} users about changes in {negocio}")
                
            except Exception as e:
                logger.error(f"Error notifying changes for negocio {negocio}: {e}")
        
        if notifications_sent > 0:
            logger.info(f"📡 Total notifications sent: {notifications_sent} negocios")
    
    async def _save_monitoring_stats(self, current_counts: Dict[str, int], changes: Dict[str, Dict]):
        """Guardar estadísticas de monitoreo en Redis"""
        try:
            stats = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_negocios_monitored": len(current_counts),
                "total_solicitudes_counted": sum(current_counts.values()),
                "changes_detected": len(changes),
                "negocios_with_changes": list(changes.keys()) if changes else [],
                "first_run": self.first_run,
                "worker_status": "running"
            }
            
            # Guardar estadísticas generales
            redis_client.set_json("firestore_monitoring:stats", stats, ttl=86400)
            
            # Guardar conteos por negocio para debugging
            redis_client.set_json("firestore_monitoring:counts", current_counts, ttl=3600)
            
            # Incrementar métrica de ciclos completados
            redis_client.increment("metric:monitoring_cycles", ttl=86400)
            
        except Exception as e:
            logger.error(f"Error saving monitoring stats: {e}")
    
    async def force_check(self) -> Dict:
        """
        Forzar una verificación inmediata (para testing o admin)
        
        Returns:
            Dict con resultado de la verificación
        """
        try:
            logger.info("🔍 Force check requested...")
            
            # Guardar estado anterior del first_run
            was_first_run = self.first_run
            
            # Ejecutar ciclo de monitoreo
            await self._monitor_cycle()
            
            # Obtener estadísticas
            stats = redis_client.get_json("firestore_monitoring:stats") or {}
            
            return {
                "success": True,
                "message": "Force check completed",
                "was_first_run": was_first_run,
                "stats": stats,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in force check: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_monitoring_status(self) -> Dict:
        """Obtener estado actual del monitoreo"""
        try:
            # Estadísticas de Redis
            stats = redis_client.get_json("firestore_monitoring:stats") or {}
            counts = redis_client.get_json("firestore_monitoring:counts") or {}
            last_update = redis_client.get_json("firestore_monitoring:last_update")
            
            # Estadísticas de WebSocket
            ws_stats = websocket_manager.get_active_connections_stats()
            
            return {
                "worker_running": self.running,
                "check_interval_seconds": self.check_interval,
                "first_run": self.first_run,
                "known_negocios": list(self.known_negocios),
                "last_update": last_update,
                "latest_stats": stats,
                "current_counts": counts,
                "websocket_connections": ws_stats,
                "redis_health": redis_client.ping()
            }
            
        except Exception as e:
            logger.error(f"Error getting monitoring status: {e}")
            return {
                "error": str(e),
                "worker_running": self.running
            }

# Instancia global del worker
firestore_monitoring_worker = FirestoreMonitoringWorker()