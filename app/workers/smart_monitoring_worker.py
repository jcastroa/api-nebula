# app/workers/smart_monitoring_worker.py
"""
Worker mejorado con sistema de priorización de citas médicas
"""
import asyncio
from typing import Dict, List, Set, Optional
import logging
from datetime import datetime, timedelta, date
from enum import Enum

from app.services.firestore_service import FirestoreService
from app.core.redis_client import redis_client
from app.websocket.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

class PriorityLevel(Enum):
    CRITICAL = "CRITICAL"  # < 15 min
    HIGH = "HIGH"          # 15-30 min  
    MEDIUM = "MEDIUM"      # 30-60 min
    NORMAL = "NORMAL"      # > 60 min
    PAST_DUE = "PAST_DUE"  # Ya pasada

class SmartFirestoreMonitoringWorker:
    """
    Worker inteligente que monitorea Firestore y calcula prioridades
    """
    
    def __init__(self):
        self.firestore_service = FirestoreService()
        self.running = False
        self.check_interval = 30  # segundos
        
        # Cache de estados anteriores
        self.previous_appointments = {}
        self.previous_priorities = {}
        
    async def start(self):
        """Iniciar el worker inteligente"""
        if self.running:
            return
            
        self.running = True
        logger.info("🧠 Starting Smart Monitoring Worker...")
        
        while self.running:
            try:
                await self._smart_monitor_cycle()
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in smart monitoring: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _smart_monitor_cycle(self):
        """Ciclo de monitoreo inteligente"""

        logger.debug("🔍 Starting monitoring cycle...")
        
        # 1. Obtener SOLO citas de hoy y futuras reprogramadas
        today_appointments = await self._get_relevant_appointments()
        logger.info(f"📊 Se encontraron  {len(today_appointments)} citas")

        # Mostrar today_appointments
        logger.info("=== TODAY_APPOINTMENTS ===")
        for negocio, appointments in today_appointments.items():
            logger.info(f"Negocio: {negocio} - Total citas: {len(appointments)}")
            for i, apt in enumerate(appointments):
                logger.info(f"  [{i+1}] ID: {apt.get('id')} - Fecha: {apt.get('fecha')} - Estado: {apt.get('estado')}")
        
        # 2. Calcular prioridades para cada cita
        appointments_with_priority = self._calculate_priorities(today_appointments)

        # Mostrar appointments_with_priority
        logger.info("=== APPOINTMENTS_WITH_PRIORITY ===")
        for negocio, appointments in appointments_with_priority.items():
            logger.info(f"Negocio: {negocio} - Total citas: {len(appointments)}")
            for i, apt in enumerate(appointments):
                priority_info = apt.get('priority', {})
                logger.info(f"  [{i+1}] ID: {apt.get('id')} - Prioridad: {priority_info.get('level')} - Score: {priority_info.get('score')}")
        
        # 3. Detectar cambios significativos
        changes = self._detect_intelligent_changes(appointments_with_priority)

        logger.info("=== CHANGES DETECTADOS ===")
        if not changes:
            logger.info("No se detectaron cambios significativos")
        else:
            for negocio, change_types in changes.items():
                logger.info(f"Negocio: {negocio}")
                for change_type, items in change_types.items():
                    if items:  # Solo mostrar categorías con cambios
                        logger.info(f"  {change_type}: {len(items)} items")
                        for item in items:
                            logger.info(f"    - ID: {item.get('id')} - Fecha: {item.get('fecha')}")

        logger.info("=== FIN DE ANÁLISIS ===")
        
        # 4. Actualizar cache
        await self._update_cache(appointments_with_priority)
        
        # 5. Notificar solo si hay cambios relevantes
        if changes:
            await self._notify_smart_changes(changes)

        logger.debug(f"✅ Monitoring cycle completed. Checked {len(today_appointments)} citas")
    
    async def _get_relevant_appointments(self) -> Dict[str, List]:
        """Obtener solo citas relevantes (hoy + reprogramadas)"""
        
        try:
            # Query optimizada para Firestore
            #today = date.today()
            today = datetime.today().strftime("%d/%m/%Y")
            
            all_negocios = {}
            negocios = await self.firestore_service.get_all_active_negocios()

            logger.info(f"Se encontraron  {len(negocios)} negocios")
            
            for negocio in negocios:
                # Query compuesta: fecha_cita = hoy 
                query_today = self.firestore_service.db.collection("citas") \
                    .where("codigo_negocio", "==", negocio) \
                    .where("fecha", "==", today) \
                    .where("estado", "in", ["pendiente", "confirmada"])
                
                
                # Combinar resultados
                appointments = []
                
                for doc in query_today.stream():
                    data = doc.to_dict()
                    data['id'] = doc.id
                    appointments.append(data)
                
                
                if appointments:
                    all_negocios[negocio] = appointments
                    
            return all_negocios
            
        except Exception as e:
            logger.error(f"Error getting relevant appointments: {e}")
            return {}
    
    def _calculate_priorities(self, appointments_by_negocio: Dict) -> Dict:
        """Calcular prioridad para cada cita"""
        
        prioritized = {}
        now = datetime.now()
        
        for negocio, appointments in appointments_by_negocio.items():
            prioritized[negocio] = []
            
            for appointment in appointments:
                # Parsear hora de la cita
                try:
                    fecha_cita = datetime.strptime(appointment.get('fecha'), "%d/%m/%Y")
                    hora_cita = appointment.get('hora', '00:00')
                    
                    # Combinar fecha y hora
                    hora_parts = hora_cita.split(':')
                    cita_datetime = fecha_cita.replace(
                        hour=int(hora_parts[0]),
                        minute=int(hora_parts[1]) if len(hora_parts) > 1 else 0
                    )
                    
                    # Calcular minutos hasta la cita
                    time_diff = cita_datetime - now
                    minutes_until = time_diff.total_seconds() / 60
                    
                    # Determinar prioridad
                    priority = self._determine_priority(
                        minutes_until
                    )
                    
                    # Agregar prioridad a la cita
                    appointment['priority'] = priority
                    appointment['minutes_until'] = minutes_until
                    appointment['calculated_at'] = now.isoformat()
                    
                    prioritized[negocio].append(appointment)
                    
                except Exception as e:
                    logger.error(f"Error calculating priority for appointment {appointment.get('id')}: {e}")
                    appointment['priority'] = {
                        'level': PriorityLevel.NORMAL.value,
                        'score': 0,
                        'reason': 'Error en cálculo'
                    }
                    prioritized[negocio].append(appointment)
        
        return prioritized
    
    def _determine_priority(self, minutes_until: float) -> Dict:
        """Determinar nivel de prioridad basado en múltiples factores"""
        
        # Cita ya pasada
        if minutes_until < -30:
            return {
                'level': PriorityLevel.PAST_DUE.value,
                'score': 0,
                'reason': 'Cita vencida',
                'color': 'gray',
                'pulse': False,
                'sound_alert': False
            }
        
        # Crítica: < 15 minutos o urgente
        if minutes_until <= 15:
            return {
                'level': PriorityLevel.CRITICAL.value,
                'score': 100 - max(0, minutes_until),
                'reason': f'⏰ En {int(max(0, minutes_until))} minutos',
                'color': 'red',
                'pulse': True,
                'sound_alert': True,
                'auto_focus': True
            }
        
        # Alta: 15-30 minutos
        elif minutes_until <= 30:
            return {
                'level': PriorityLevel.HIGH.value,
                'score': 85 - (minutes_until - 15),
                'reason': f'Próxima: {int(minutes_until)} min',
                'color': 'orange',
                'pulse': False,
                'sound_alert': False,
                'auto_focus': False
            }
        
        # Media: 30-60 
        elif minutes_until <= 60 :
            return {
                'level': PriorityLevel.MEDIUM.value,
                'score': 70 - max(0, (minutes_until - 30) / 2),
                'reason': f'En {int(minutes_until)} min',
                'color': 'yellow', 
                'pulse': False,
                'sound_alert': False,
                'auto_focus': False
            }
        
        # Normal: > 60 minutos
        else:
            hours = int(minutes_until / 60)
            return {
                'level': PriorityLevel.NORMAL.value,
                'score': max(10, 40 - hours * 5),
                'reason': f'En {hours}h {int(minutes_until % 60)}m',
                'color': 'blue',
                'pulse': False,
                'sound_alert': False,
                'auto_focus': False
            }
    
    def _detect_intelligent_changes(self, current_appointments: Dict) -> Dict:
        """Detectar solo cambios significativos"""
        
        all_changes = {}
        
        for negocio, appointments in current_appointments.items():
            changes = {
                'new_critical': [],      # Nuevas citas críticas
                'became_critical': [],    # Citas que pasaron a críticas
                'new_appointments': [],   # Nuevas citas normales
                'priority_upgraded': [],  # Subieron de prioridad
                'status_changed': [],     # Cambios de estado
                'rescheduled': []        # Reprogramadas
            }
            
            previous = self.previous_appointments.get(negocio, {})
            
            for appointment in appointments:
                app_id = appointment['id']
                current_priority = appointment['priority']['level']
                
                # Verificar si es nueva
                if app_id not in previous:
                    if current_priority == PriorityLevel.CRITICAL.value:
                        changes['new_critical'].append(appointment)
                    else:
                        changes['new_appointments'].append(appointment)
                else:
                    # Comparar con estado anterior
                    prev_appointment = previous[app_id]
                    prev_priority = self.previous_priorities.get(f"{negocio}:{app_id}")
                    
                    # Cambio de prioridad
                    if prev_priority and prev_priority != current_priority:
                        if current_priority == PriorityLevel.CRITICAL.value:
                            changes['became_critical'].append(appointment)
                        elif self._is_priority_upgrade(prev_priority, current_priority):
                            changes['priority_upgraded'].append(appointment)
                    
                    # Cambio de estado
                    if prev_appointment.get('estado') != appointment.get('estado'):
                        changes['status_changed'].append(appointment)
                    
                    # Fue reprogramada
                    # if not prev_appointment.get('fue_reprogramada') and appointment.get('fue_reprogramada'):
                    #     changes['rescheduled'].append(appointment)
            
            # Solo agregar si hay cambios
            if any(changes.values()):
                all_changes[negocio] = changes
        
        return all_changes
    
    def _is_priority_upgrade(self, old_priority: str, new_priority: str) -> bool:
        """Verificar si la prioridad subió"""
        priority_order = {
            PriorityLevel.NORMAL.value: 0,
            PriorityLevel.MEDIUM.value: 1,
            PriorityLevel.HIGH.value: 2,
            PriorityLevel.CRITICAL.value: 3
        }
        
        return priority_order.get(new_priority, 0) > priority_order.get(old_priority, 0)
    
    async def _update_cache(self, appointments_with_priority: Dict):
        """Actualizar cache con nueva información"""
        
        # Actualizar previous_appointments
        self.previous_appointments = {}
        for negocio, appointments in appointments_with_priority.items():
            self.previous_appointments[negocio] = {
                app['id']: app for app in appointments
            }
            
            # Actualizar prioridades
            for app in appointments:
                key = f"{negocio}:{app['id']}"
                self.previous_priorities[key] = app['priority']['level']
        
        # Actualizar Redis con información agregada
        for negocio, appointments in appointments_with_priority.items():
            # Ordenar por score de prioridad
            sorted_apps = sorted(
                appointments,
                key=lambda x: x['priority']['score'],
                reverse=True
            )
            
            # Guardar top 10 críticas en Redis para acceso rápido
            critical_apps = [
                app for app in sorted_apps
                if app['priority']['level'] in [PriorityLevel.CRITICAL.value, PriorityLevel.HIGH.value]
            ][:10]
            
            redis_client.set_json(
                f"appointments:critical:{negocio}",
                critical_apps,
                ttl=120  # 2 minutos
            )
            
            # Estadísticas
            stats = {
                'total': len(appointments),
                'critical': len([a for a in appointments if a['priority']['level'] == PriorityLevel.CRITICAL.value]),
                'high': len([a for a in appointments if a['priority']['level'] == PriorityLevel.HIGH.value]),
                'updated_at': datetime.now().isoformat()
            }
            
            redis_client.set_json(
                f"appointments:stats:{negocio}",
                stats,
                ttl=120
            )
    
    async def _notify_smart_changes(self, changes: Dict):
        """Notificar cambios de forma inteligente"""
        
        for negocio, negocio_changes in changes.items():
            # Determinar tipo de notificación
            notification_type = self._determine_notification_type(negocio_changes)
            
            # Preparar mensaje según el tipo
            message = {
                'type': 'appointment_update',
                'notification_type': notification_type,
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'new_critical': len(negocio_changes.get('new_critical', [])),
                    'became_critical': len(negocio_changes.get('became_critical', [])),
                    'new_appointments': len(negocio_changes.get('new_appointments', [])),
                    'priority_upgraded': len(negocio_changes.get('priority_upgraded', [])),
                    'status_changed': len(negocio_changes.get('status_changed', [])),
                    'rescheduled': len(negocio_changes.get('rescheduled', []))
                }
            }
            
            # Solo incluir datos críticos si es necesario
            if notification_type in ['URGENT_ALERT', 'CRITICAL_UPDATE']:
                critical_data = (
                    negocio_changes.get('new_critical', []) +
                    negocio_changes.get('became_critical', [])
                )
                
                # Limitar información enviada
                message['critical_appointments'] = [
                    {
                        'id': app['id'],
                        'patient_name': app.get('nombre', 'Sin nombre'),
                        'time': app.get('hora'),
                        'priority': app['priority'],
                        'minutes_until': app.get('minutes_until')
                    }
                    for app in critical_data[:5]  # Máximo 5 citas críticas
                ]
            
            # Notificar via WebSocket
            await websocket_manager.notify_negocio_changes(negocio, message)
            
            logger.info(f"📡 Notified {notification_type} for negocio {negocio}")
    
    def _determine_notification_type(self, changes: Dict) -> str:
        """Determinar el tipo de notificación según los cambios"""
        
        # Prioridad de tipos de notificación
        if changes.get('new_critical') or changes.get('became_critical'):
            return 'URGENT_ALERT'
        elif changes.get('priority_upgraded'):
            return 'PRIORITY_UPDATE'
        elif changes.get('rescheduled'):
            return 'RESCHEDULED_ALERT'
        elif changes.get('new_appointments'):
            return 'NEW_APPOINTMENTS'
        elif changes.get('status_changed'):
            return 'STATUS_UPDATE'
        else:
            return 'GENERAL_UPDATE'

   
# Instancia global del worker inteligente
firestore_monitoring_worker = SmartFirestoreMonitoringWorker()