# ==========================================
# app/workers/scheduler.py - Programador de tareas
# ==========================================

"""Programador de tareas background usando schedule"""
import asyncio
import schedule
import logging
from datetime import datetime

from app.workers.cleanup_worker import CleanupWorker
from app.config import settings

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    Programador de tareas background
    """
    
    def __init__(self):
        self.cleanup_worker = CleanupWorker()
        self.running = False
        self.tasks = {}
    
    def setup_schedules(self):
        """Configurar todas las tareas programadas"""
        
        # Limpieza nocturna (configurada en settings)
        cleanup_time = getattr(settings, 'CLEANUP_SCHEDULE', '02:00')
        schedule.every().day.at(cleanup_time).do(self._run_cleanup).tag('cleanup')
        
        # Métricas cada hora
        schedule.every().hour.do(self._update_metrics).tag('metrics')
        
        # Limpieza de blacklist cada 4 horas
        schedule.every(4).hours.do(self._cleanup_blacklist).tag('blacklist')
        
        logger.info(f"📅 Scheduled tasks:")
        logger.info(f"   - Cleanup: Daily at {cleanup_time}")
        logger.info(f"   - Metrics: Every hour")
        logger.info(f"   - Blacklist cleanup: Every 4 hours")
    
    async def start(self):
        """Iniciar el scheduler"""
        if self.running:
            logger.warning("Task scheduler already running")
            return
        
        self.running = True
        self.setup_schedules()
        
        logger.info("📅 Starting task scheduler...")
        
        # Ejecutar tareas iniciales (CORRECCIÓN: llamar la versión async)
        try:
            await self._async_run_cleanup()
        except Exception as e:
            logger.error(f"Error en limpieza inicial: {e}")
        
        # Loop principal del scheduler
        while self.running:
            try:
                # Ejecutar tareas pendientes
                schedule.run_pending()
                
                # Esperar 60 segundos antes del siguiente check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)
        
        logger.info("📅 Task scheduler stopped")
    
    def stop(self):
        """Detener el scheduler"""
        self.running = False
        schedule.clear()
        logger.info("🛑 Stopping task scheduler...")
    
    def _run_cleanup(self):
        """Ejecutar tarea de limpieza (sync wrapper)"""
        # CORRECCIÓN: Crear task de forma segura
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_run_cleanup())
            else:
                loop.run_until_complete(self._async_run_cleanup())
        except Exception as e:
            logger.error(f"Error creando task de cleanup: {e}")
    
    async def _async_run_cleanup(self):
        """Ejecutar limpieza de forma asíncrona"""
        try:
            logger.info("🧹 Running scheduled cleanup...")
            
            # CORRECCIÓN: Usar métodos síncronos de Redis
            from app.core.redis_client import redis_client
            
            # Limpieza de Redis
            cleaned_activities = redis_client.cleanup_expired_activities()
            cleaned_metrics = redis_client.cleanup_old_metrics()
            cleaned_blacklist = redis_client.cleanup_blacklist_orphans()
            
            logger.info(f"✅ Redis cleanup completed:")
            logger.info(f"   - Activities: {cleaned_activities}")
            logger.info(f"   - Metrics: {cleaned_metrics}")
            logger.info(f"   - Blacklist: {cleaned_blacklist}")
            
            # Cleanup de base de datos si existe
            if hasattr(self.cleanup_worker, 'cleanup_inactive_sessions'):
                try:
                    stats = await self.cleanup_worker.cleanup_inactive_sessions()
                    logger.info(f"✅ Database cleanup completed: {stats}")
                except Exception as e:
                    logger.error(f"Error en cleanup de BD: {e}")
            
            # Incrementar métrica
            redis_client.increment("metric:scheduled_cleanups", ttl=86400)
        
        except Exception as e:
            logger.error(f"❌ Error in scheduled cleanup: {e}")
    
    def _update_metrics(self):
        """Actualizar métricas del sistema"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_update_metrics())
            else:
                loop.run_until_complete(self._async_update_metrics())
        except Exception as e:
            logger.error(f"Error creando task de metrics: {e}")
    
    async def _async_update_metrics(self):
        """Actualizar métricas de forma asíncrona"""
        try:
            from app.core.redis_client import redis_client
            
            # Obtener estadísticas básicas
            timestamp = datetime.utcnow().isoformat()
            
            # Obtener stats de Redis
            redis_health = redis_client.health_check()
            
            metrics_data = {
                "timestamp": timestamp,
                "redis": redis_health,
                "scheduler_run": True
            }
            
            # Intentar obtener stats de BD si están disponibles
            try:
                from app.crud.session import SessionCRUD
                from app.crud.user import UserCRUD
                
                # Nota: Estas líneas pueden fallar si no tienes BD configurada
                session_crud = SessionCRUD()
                user_crud = UserCRUD()
                metrics_data["sessions"] = await session_crud.get_session_stats()
                metrics_data["total_users"] = await user_crud.count()
                
            except Exception as e:
                logger.warning(f"BD stats no disponibles: {e}")
                metrics_data["database"] = "unavailable"
            
            # Guardar métricas
            redis_client.set_json("metrics:hourly", metrics_data, ttl=90000)
            logger.debug(f"📊 Metrics updated at {timestamp}")
            
        except Exception as e:
            logger.error(f"❌ Error updating metrics: {e}")

    def _cleanup_blacklist(self):
        """Limpiar blacklist antigua"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_cleanup_blacklist())
            else:
                loop.run_until_complete(self._async_cleanup_blacklist())
        except Exception as e:
            logger.error(f"Error creando task de blacklist cleanup: {e}")
    
    async def _async_cleanup_blacklist(self):
        """Limpiar tokens blacklist expirados"""
        try:
            from app.core.redis_client import redis_client
            
            # Usar el método de limpieza incorporado
            cleaned_count = redis_client.cleanup_blacklist_orphans()
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned {cleaned_count} orphaned blacklist entries")
            
            # Incrementar métrica
            redis_client.increment("metric:blacklist_cleanups", ttl=86400)
            
        except Exception as e:
            logger.error(f"❌ Error cleaning blacklist: {e}")

            
    def get_schedule_info(self) -> list:
        """Obtener información de tareas programadas"""
        jobs = []
        try:
            for job in schedule.jobs:
                jobs.append({
                    "job": str(job.job_func),
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "interval": str(job.interval),
                    "unit": job.unit,
                    "tags": list(job.tags)
                })
        except Exception as e:
            logger.error(f"Error obteniendo info de schedule: {e}")
        return jobs

# Instancia global del scheduler
task_scheduler = TaskScheduler()

async def start_background_tasks():
    """
    Función para iniciar todas las tareas background
    Llamada desde main.py en startup
    """
    
    logger.info("🚀 Starting background tasks...")
    
    # Iniciar scheduler en background
    asyncio.create_task(task_scheduler.start())
    
    logger.info("✅ Background tasks started")

async def stop_background_tasks():
    """
    Función para detener todas las tareas background
    Llamada desde main.py en shutdown
    """
    
    logger.info("🛑 Stopping background tasks...")
    
    task_scheduler.stop()
    
    logger.info("✅ Background tasks stopped")