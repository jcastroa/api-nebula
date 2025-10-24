# app/api/v1/endpoints/negocios_smart.py
"""
Endpoints mejorados para gestión de citas con priorización inteligente
y CRUD de negocios
"""
from enum import Enum
import math
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any, List
import logging
import json
from datetime import datetime, date, timedelta

from app.services.firestore_service import FirestoreService
from app.services.consultorio_service import ConsultorioService
from app.websocket.websocket_manager import websocket_manager
from app.dependencies import get_current_user
from app.core.redis_client import redis_client
from app.config import settings
from app.core.security import (
    create_access_token,
)
from app.schemas.negocio import (
    NegocioCreate,
    NegocioUpdate,
    NegocioEstadoUpdate,
    NegocioResponse,
    NegocioListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negocios")

def get_firestore_service() -> FirestoreService:
    return FirestoreService()

class DateFilter(str, Enum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    WEEK = "week"
    ALL = "all"

def get_date_range(date_filter: DateFilter):
    """
    Retorna el rango de fechas según el filtro seleccionado
    """
    today = datetime.now()

    if date_filter == DateFilter.TODAY:
        start_date = today
        end_date = today
    elif date_filter == DateFilter.TOMORROW:
        tomorrow = today + timedelta(days=1)
        start_date = tomorrow
        end_date = tomorrow
    elif date_filter == DateFilter.WEEK:
        start_date = today
        end_date = today + timedelta(days=7)
    else:  # ALL
        start_date = today - timedelta(days=30)  # Últimos 30 días
        end_date = today + timedelta(days=30)   # Próximos 30 días

    return start_date, end_date


# ==========================================
# ENDPOINTS CRUD PARA GESTIÓN DE NEGOCIOS
# Estos deben ir PRIMERO para evitar conflictos
# ==========================================

@router.get("/", response_model=NegocioListResponse)
async def listar_negocios(
    search: Optional[str] = Query(None, description="Término de búsqueda (nombre, RUC, email)"),
    activo_only: bool = Query(False, description="Filtrar solo negocios activos"),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Listar todos los negocios con búsqueda opcional desde MariaDB

    Args:
        search: Término de búsqueda para filtrar por nombre, RUC o email
        activo_only: Si es True, solo retorna negocios activos

    Returns:
        Lista de negocios con sus datos completos e indicador de existencia en Firestore
    """
    try:
        logger.info(f"Listing negocios from MariaDB - search: {search}, activo_only: {activo_only}")

        # Obtener negocios de MariaDB
        consultorios = ConsultorioService.get_all_consultorios(
            search_term=search,
            activo_only=activo_only
        )

        # Agregar indicador de existencia en Firestore
        for consultorio in consultorios:
            consultorio['existe_en_firestore'] = ConsultorioService.verificar_existe_en_firestore(
                consultorio['id'],
                firestore_service
            )

        return {
            "success": True,
            "total": len(consultorios),
            "data": consultorios,
            "message": f"Se encontraron {len(consultorios)} negocios"
        }

    except Exception as e:
        logger.error(f"Error listing negocios: {e}")
        raise HTTPException(status_code=500, detail=f"Error al listar negocios: {str(e)}")


@router.post("/", response_model=Dict[str, Any])
async def crear_negocio(
    negocio_data: NegocioCreate,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Crear un nuevo negocio en MariaDB

    Args:
        negocio_data: Datos del negocio a crear

    Returns:
        ID del negocio creado y sus datos
    """
    try:
        logger.info(f"Creating negocio in MariaDB: {negocio_data.nombre}")

        # Convertir schema a dict
        negocio_dict = negocio_data.dict()

        # Crear negocio en MariaDB
        negocio_id = ConsultorioService.create_consultorio(negocio_dict)

        # Obtener el negocio creado para retornarlo
        negocio = ConsultorioService.get_consultorio_by_id(negocio_id)

        # Verificar si existe en Firestore
        negocio['existe_en_firestore'] = ConsultorioService.verificar_existe_en_firestore(
            negocio_id,
            firestore_service
        )

        return {
            "success": True,
            "id": negocio_id,
            "data": negocio,
            "message": f"Negocio '{negocio_data.nombre}' creado exitosamente"
        }

    except Exception as e:
        logger.error(f"Error creating negocio: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear negocio: {str(e)}")


# ==========================================
# ENDPOINTS DE CITAS PRIORIZADAS
# Estos tienen paths específicos y deben ir antes de los endpoints genéricos /{negocio_id}
# ==========================================

@router.get("/{codigo_negocio}/citas-priorizadas")
async def get_citas_priorizadas(
    codigo_negocio: str,
    date_filter: DateFilter = Query(DateFilter.TODAY, description="Filtro de fecha"),
    include_past: bool = Query(False, description="Incluir citas pasadas"),
    min_priority: Optional[str] = Query(None, description="Prioridad mínima (NORMAL, MEDIUM, HIGH, CRITICAL)"),
    search: Optional[str] = Query(None, description="Buscar por nombre de cliente o servicio"),
    page: int = Query(1, description="Número de página", ge=1),
    items_per_page: int = Query(10, description="Items por página", ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Obtener citas del día con priorización calculada y paginación

    Returns:
        - Lista de citas ordenadas por prioridad (paginada)
        - Información de prioridad para cada cita
        - Estadísticas de urgencia
        - Información de paginación
    """
    try:
        logger.info(f"Getting prioritized appointments for negocio {codigo_negocio}, page {page}")

        # 1. Verificar cache de citas críticas primero
        cached_critical = redis_client.get_json(f"appointments:critical:{codigo_negocio}")

        # 2. Obtener citas del día desde Firestore
        #today = datetime.today().strftime("%d/%m/%Y")  # "23/09/2025"
        # 2. Obtener rango de fechas según el filtro
        start_date, end_date = get_date_range(date_filter)

        # Query para citas de hoy
        # query = firestore_service.db.collection("citas") \
        #     .where("codigo_negocio", "==", codigo_negocio) \
        #     .where("fecha", "==", today)
        query = firestore_service.db.collection("citas") \
            .where("codigo_negocio", "==", codigo_negocio)

        # 4. Aplicar filtros de fecha
        # 4. Para filtros específicos, aplicar filtro en Firestore (más eficiente)
        if date_filter == DateFilter.TODAY:
            today_str = start_date.strftime("%d/%m/%Y")
            query = query.where("fecha", "==", today_str)
        elif date_filter == DateFilter.TOMORROW:
            tomorrow_str = start_date.strftime("%d/%m/%Y")
            query = query.where("fecha", "==", tomorrow_str)
        # Para WEEK y ALL se filtrará después del procesamiento

        if not include_past:
            query = query.where("estado", "in", ["pendiente", "confirmada"])

        # Ejecutar query
        docs = query.stream()
        appointments = []

        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            appointments.append(data)

        # 4. Calcular prioridad para cada cita
        now = datetime.now()
        prioritized_appointments = []

        for appointment in appointments:
            try:
                # Parsear hora de la cita
                fecha_cita = datetime.strptime(appointment.get('fecha'), "%d/%m/%Y")

                # Aplicar filtros de fecha para WEEK y ALL
                if date_filter == DateFilter.WEEK:
                    if start_date and end_date:
                        if not (start_date.date() <= fecha_cita.date() <= end_date.date()):
                            continue

                # Aplicar filtro de búsqueda
                if search:
                    search_lower = search.lower()
                    cliente_nombre = appointment.get('nombre', '').lower()
                    telefono = appointment.get('telefono', '').lower()

                    if search_lower not in cliente_nombre and search_lower not in telefono:
                        continue

                hora_cita = appointment.get('hora', '00:00')
                hora_parts = hora_cita.split(':')

                cita_datetime = fecha_cita.replace(
                    hour=int(hora_parts[0]),
                    minute=int(hora_parts[1]) if len(hora_parts) > 1 else 0
                )

                # Calcular tiempo hasta la cita
                time_diff = cita_datetime - now
                minutes_until = time_diff.total_seconds() / 60

                # Calcular prioridad
                priority = calculate_priority(minutes_until)

                appointment['priority'] = priority
                appointment['minutes_until'] = round(minutes_until, 1)
                appointment['appointment_datetime'] = cita_datetime.isoformat()
                appointment['pago_status'] = get_pago_status(appointment)

                # Filtrar por prioridad mínima si se especifica
                if min_priority:
                    priority_levels = ['NORMAL', 'MEDIUM', 'HIGH', 'CRITICAL']
                    min_index = priority_levels.index(min_priority)
                    current_index = priority_levels.index(priority['level'])

                    if current_index >= min_index:
                        prioritized_appointments.append(appointment)
                else:
                    prioritized_appointments.append(appointment)

            except Exception as e:
                logger.error(f"Error processing appointment {appointment.get('id')}: {e}")
                appointment['priority'] = {
                    'level': 'NORMAL',
                    'score': 0,
                    'reason': 'Error en cálculo'
                }
                prioritized_appointments.append(appointment)

        # 5. Ordenar por score de prioridad (mayor a menor)
        prioritized_appointments.sort(
            key=lambda x: x['priority']['score'],
            reverse=True
        )

        # 6. Aplicar paginación
        total_items = len(prioritized_appointments)
        total_pages = math.ceil(total_items / items_per_page) if total_items > 0 else 1

        # Calcular índices para la paginación
        start_index = (page - 1) * items_per_page
        end_index = start_index + items_per_page

        # Obtener items de la página actual
        paginated_appointments = prioritized_appointments[start_index:end_index]

        # 7. Calcular estadísticas (sobre todos los datos, no solo la página actual)
        stats = {
            'total': total_items,
            'urgentes': len([a for a in prioritized_appointments
                           if a['priority']['level'] == 'CRITICAL']),
            'proximas': len([a for a in prioritized_appointments
                           if a['priority']['level'] == 'HIGH']),
            'por_confirmar': len([a for a in prioritized_appointments
                                if a['estado'] == 'pendiente']),
            'sin_pago': len([
                a for a in prioritized_appointments
                if not a.get('pago')  # no tiene pago
                or not a['pago'].get('realizado', False)  # no se realizó
                or not a['pago'].get('validado', False)   # realizado pero no validado
            ]),
            'concluidas': len([a for a in prioritized_appointments
                            if a['estado'] == 'completada'])
        }

        # 8. Guardar en cache para acceso rápido
        if stats['urgentes'] > 0:
            redis_client.set_json(
                f"appointments:critical:{codigo_negocio}",
                prioritized_appointments[:10],  # Top 10
                ttl=120
            )

        return {
            "success": True,
            "total": total_items,
            "currentPage": page,
            "itemsPerPage": items_per_page,
            "totalPages": total_pages,
            "data": {
                "appointments": paginated_appointments,
                "stats": stats,
                "cached_critical": cached_critical is not None,
                "timestamp": now.isoformat(),
                "codigo_negocio": codigo_negocio
            },
            "message": f"Retrieved {len(paginated_appointments)} prioritized appointments (page {page} of {total_pages})"
        }

    except Exception as e:
        logger.error(f"Error getting prioritized appointments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{codigo_negocio}/smart-refresh")
async def smart_refresh(
    codigo_negocio: str,
    last_update: Optional[str] = Query(None, description="Timestamp de última actualización"),
    editing_ids: List[str] = Query(None, description="IDs siendo editados actualmente"),
    active_filters: Optional[str] = Query(None, description="Filtros activos (JSON)"),
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Refresh inteligente que respeta el contexto del usuario

    - No actualiza registros siendo editados
    - Mantiene filtros activos
    - Retorna solo cambios desde last_update
    - Incluye información de prioridad
    """
    try:
        logger.info(f"Smart refresh for negocio {codigo_negocio}, editing: {editing_ids}")

        # 1. Obtener citas priorizadas
        result = await get_citas_priorizadas(
            codigo_negocio=codigo_negocio,
            include_past=False,
            current_user=current_user,
            firestore_service=firestore_service
        )

        appointments = result['data']['appointments']

        # 2. Excluir citas siendo editadas
        if editing_ids:
            appointments_to_update = [
                app for app in appointments
                if app['id'] not in editing_ids
            ]
            excluded_count = len(appointments) - len(appointments_to_update)
        else:
            appointments_to_update = appointments
            excluded_count = 0

        # 3. Detectar cambios desde last_update
        changes = {
            'new': [],
            'updated': [],
            'priority_changed': [],
            'total_changes': 0
        }

        if last_update:
            try:
                last_update_dt = datetime.fromisoformat(last_update)

                for app in appointments_to_update:
                    # Verificar si es nuevo o actualizado
                    updated_at = app.get('updated_at')
                    created_at = app.get('created_at')

                    if created_at and datetime.fromisoformat(created_at) > last_update_dt:
                        changes['new'].append(app['id'])
                    elif updated_at and datetime.fromisoformat(updated_at) > last_update_dt:
                        changes['updated'].append(app['id'])

                    # Verificar cambios de prioridad (basado en minutes_until)
                    if app['priority']['level'] in ['CRITICAL', 'HIGH']:
                        changes['priority_changed'].append(app['id'])

                changes['total_changes'] = len(changes['new']) + len(changes['updated'])

            except Exception as e:
                logger.warning(f"Error parsing last_update: {e}")

        # 4. Aplicar filtros si existen
        if active_filters:
            try:
                filters = json.loads(active_filters)
                # Aplicar filtros a appointments_to_update
                # Ejemplo: filtrar por estado, prioridad, etc.
                if 'priority' in filters:
                    appointments_to_update = [
                        app for app in appointments_to_update
                        if app['priority']['level'] == filters['priority']
                    ]
                if 'estado' in filters:
                    appointments_to_update = [
                        app for app in appointments_to_update
                        if app.get('estado') == filters['estado']
                    ]
            except Exception as e:
                logger.warning(f"Error parsing filters: {e}")

        # 5. Preparar respuesta inteligente
        response = {
            "success": True,
            "data": {
                "appointments": appointments_to_update,
                "stats": result['data']['stats'],
                "changes_summary": changes,
                "excluded_for_editing": excluded_count,
                "timestamp": datetime.now().isoformat(),
                "partial_update": bool(editing_ids),
                "filters_applied": bool(active_filters)
            },
            "action_suggested": determine_action(changes, result['data']['stats'])
        }

        return response

    except Exception as e:
        logger.error(f"Error in smart refresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/{codigo_negocio}/smart-ws")
async def smart_websocket_endpoint(
    websocket: WebSocket,
    codigo_negocio: str,
    token: str = Query(..., description="Access token")
):
    """
    WebSocket endpoint mejorado con notificaciones inteligentes
    """
    try:
        # Verificar autenticación
        from app.core.security import verify_token
        from app.dependencies import get_user_crud

        try:
            payload = verify_token(token)
            user_crud = get_user_crud()
            user = await user_crud.get(payload['user_id'])

            if not user:
                await websocket.close(code=4001, reason="Invalid user")
                return

        except Exception as e:
            logger.warning(f"WebSocket auth failed: {e}")
            await websocket.close(code=4001, reason="Authentication failed")
            return

        user_id = user['id']
        user_info = {
            "username": user.get('username'),
            "email": user.get('email'),
            "connected_at": datetime.now().isoformat()
        }

        # Conectar al WebSocket manager
        await websocket_manager.connect(websocket, user_id, codigo_negocio, user_info)

        logger.info(f"🔌 Smart WebSocket connected: user {user_id} to negocio {codigo_negocio}")

        # Enviar estado inicial
        await websocket.send_json({
            "type": "connection_established",
            "message": f"Conectado a sistema de citas inteligente",
            "negocio": codigo_negocio,
            "features": {
                "priority_alerts": True,
                "smart_refresh": True,
                "editing_protection": True
            },
            "timestamp": datetime.now().isoformat()
        })

        try:
            while True:
                # Recibir mensajes del cliente
                data = await websocket.receive_text()

                try:
                    message = json.loads(data)

                    # Manejar diferentes tipos de mensajes
                    if message.get('type') == 'editing_start':
                        # Cliente informa que comenzó a editar
                        appointment_id = message.get('appointment_id')
                        logger.debug(f"User {user_id} started editing {appointment_id}")

                    elif message.get('type') == 'editing_end':
                        # Cliente terminó de editar
                        appointment_id = message.get('appointment_id')
                        logger.debug(f"User {user_id} finished editing {appointment_id}")

                    elif message.get('type') == 'request_critical':
                        # Cliente solicita solo citas críticas
                        cached_critical = redis_client.get_json(
                            f"appointments:critical:{codigo_negocio}"
                        )

                        await websocket.send_json({
                            "type": "critical_appointments",
                            "data": cached_critical or [],
                            "timestamp": datetime.now().isoformat()
                        })

                    elif message.get('type') == 'pong':
                        # Respuesta a ping
                        pass

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from user {user_id}: {data}")

        except WebSocketDisconnect:
            logger.info(f"🔌 Smart WebSocket disconnected: user {user_id}")

        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")

        finally:
            await websocket_manager.disconnect(user_id, codigo_negocio)

    except Exception as e:
        logger.error(f"WebSocket setup error: {e}")
        try:
            await websocket.close(code=4000, reason="Server error")
        except:
            pass

@router.get("/{codigo_negocio}/ws-token")
async def get_websocket_token(
    codigo_negocio: str,
    current_user: dict = Depends(get_current_user)  # Usa cookie httpOnly
):
    """
    Generar token temporal para WebSocket (24 horas de duración)
    """
    # Crear token simple con duración larga
    ws_token_data = {
        "user_id": current_user['id'],
        "username": current_user['username'],
        "codigo_negocio": codigo_negocio,
        "type": "websocket",
        "exp": datetime.utcnow() + timedelta(hours=24)  # 24 horas
    }

    ws_token = create_access_token(ws_token_data)

    # Guardar en Redis para validación
    redis_client.set_json(
        f"ws_token:{current_user['id']}:{codigo_negocio}",
        {
            "token": ws_token,
            "created_at": datetime.utcnow().isoformat()
        },
        ttl=86400  # 24 horas
    )

    return {
        "ws_token": ws_token,
        "expires_in": 86400
    }


# ==========================================
# ENDPOINTS DE ACTUALIZACIÓN Y CONSULTA DE NEGOCIOS INDIVIDUALES
# Estos deben ir AL FINAL porque son más genéricos
# ==========================================

@router.patch("/{negocio_id}/estado", response_model=Dict[str, Any])
async def cambiar_estado_negocio(
    negocio_id: int,
    estado_data: NegocioEstadoUpdate,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Cambiar el estado activo/inactivo de un negocio en MariaDB

    Args:
        negocio_id: ID del negocio
        estado_data: Nuevo estado (activo: true/false)

    Returns:
        Datos actualizados del negocio con indicador de existencia en Firestore
    """
    try:
        logger.info(f"Changing estado for negocio {negocio_id} to {estado_data.activo}")

        # Verificar que el negocio existe
        negocio_existente = ConsultorioService.get_consultorio_by_id(negocio_id)
        if not negocio_existente:
            raise HTTPException(
                status_code=404,
                detail=f"Negocio con ID {negocio_id} no encontrado"
            )

        # Cambiar estado en MariaDB
        success = ConsultorioService.cambiar_estado_consultorio(
            negocio_id,
            estado_data.activo
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error al cambiar el estado del negocio"
            )

        # Obtener negocio actualizado
        negocio_actualizado = ConsultorioService.get_consultorio_by_id(negocio_id)

        # Verificar si existe en Firestore
        negocio_actualizado['existe_en_firestore'] = ConsultorioService.verificar_existe_en_firestore(
            negocio_id,
            firestore_service
        )

        estado_texto = "activado" if estado_data.activo else "desactivado"

        return {
            "success": True,
            "data": negocio_actualizado,
            "message": f"Negocio {estado_texto} exitosamente"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing estado for negocio {negocio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al cambiar estado: {str(e)}")


@router.put("/{negocio_id}", response_model=Dict[str, Any])
async def actualizar_negocio(
    negocio_id: int,
    negocio_data: NegocioUpdate,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Actualizar un negocio existente en MariaDB

    Args:
        negocio_id: ID del negocio a actualizar
        negocio_data: Datos a actualizar (solo los campos proporcionados)

    Returns:
        Datos actualizados del negocio con indicador de existencia en Firestore
    """
    try:
        logger.info(f"Updating negocio in MariaDB: {negocio_id}")

        # Verificar que el negocio existe
        negocio_existente = ConsultorioService.get_consultorio_by_id(negocio_id)
        if not negocio_existente:
            raise HTTPException(
                status_code=404,
                detail=f"Negocio con ID {negocio_id} no encontrado"
            )

        # Convertir a dict y remover campos None (solo actualizar campos proporcionados)
        update_dict = negocio_data.dict(exclude_unset=True)

        if not update_dict:
            raise HTTPException(
                status_code=400,
                detail="No se proporcionaron campos para actualizar"
            )

        # Actualizar negocio en MariaDB
        success = ConsultorioService.update_consultorio(negocio_id, update_dict)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar el negocio"
            )

        # Obtener negocio actualizado
        negocio_actualizado = ConsultorioService.get_consultorio_by_id(negocio_id)

        # Verificar si existe en Firestore
        negocio_actualizado['existe_en_firestore'] = ConsultorioService.verificar_existe_en_firestore(
            negocio_id,
            firestore_service
        )

        return {
            "success": True,
            "data": negocio_actualizado,
            "message": f"Negocio actualizado exitosamente"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating negocio {negocio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar negocio: {str(e)}")


@router.get("/{negocio_id}", response_model=Dict[str, Any])
async def obtener_negocio(
    negocio_id: int,
    current_user: dict = Depends(get_current_user),
    firestore_service: FirestoreService = Depends(get_firestore_service)
):
    """
    Obtener un negocio específico por ID desde MariaDB

    Args:
        negocio_id: ID del negocio a obtener

    Returns:
        Datos completos del negocio con indicador de existencia en Firestore
    """
    try:
        logger.info(f"Getting negocio from MariaDB: {negocio_id}")

        # Obtener negocio de MariaDB
        negocio = ConsultorioService.get_consultorio_by_id(negocio_id)

        if not negocio:
            raise HTTPException(
                status_code=404,
                detail=f"Negocio con ID {negocio_id} no encontrado"
            )

        # Verificar si existe en Firestore
        negocio['existe_en_firestore'] = ConsultorioService.verificar_existe_en_firestore(
            negocio_id,
            firestore_service
        )

        return {
            "success": True,
            "data": negocio,
            "message": "Negocio encontrado"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting negocio {negocio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener negocio: {str(e)}")


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def calculate_priority(minutes_until: float) -> Dict:
    """Calcular prioridad de una cita"""

    if minutes_until < -30:
        return {
            'level': 'PAST_DUE',
            'score': 0,
            'reason': 'Cita vencida',
            'color': '#6B7280',  # gray
            'pulse': False,
            'sound_alert': False
        }

    if minutes_until <= 15:
        return {
            'level': 'CRITICAL',
            'score': 100 - max(0, minutes_until),
            'reason': f'⏰ En {int(max(0, minutes_until))} min',
            'color': '#EF4444',  # red
            'pulse': True,
            'sound_alert': True,
            'badge': '🚨 URGENTE'
        }

    elif minutes_until <= 30:
        return {
            'level': 'HIGH',
            'score': 85 - (minutes_until - 15),
            'reason': f'Próxima: {int(minutes_until)} min',
            'color': '#F97316',  # orange
            'pulse': False,
            'sound_alert': False,
            'badge': '⚠️ PRÓXIMA'
        }

    elif minutes_until <= 60 :
            return {
                'level': 'MEDIUM',
                'score': 70 - max(0, (minutes_until - 30) / 2),
                'reason': f'En {int(minutes_until)} min',
                'color': 'yellow',
                'pulse': False,
                'sound_alert': False,
                'badge': '🟡 Por confirmar'
            }



    else:
        hours = int(minutes_until / 60)
        mins = int(minutes_until % 60)
        return {
            'level': 'NORMAL',
            'score': max(10, 40 - hours * 5),
            'reason': f'En {hours}h {mins}m',
            'color': '#3B82F6',  # blue
            'pulse': False,
            'sound_alert': False,
            'badge': '🟡 Por confirmar'
        }

def get_pago_status(appointment: Dict) -> Dict:
    """
    Determinar estado del pago basado en la estructura real
    """
    pago = appointment.get('pago')

    # No hay objeto pago o no requiere pago
    if not pago :
        return {
             'status': 'pending',
            'emoji': '⚪',
            'text': 'Sin pago',
            'color': 'red'
        }

    # Verificar si el pago fue realizado
    if pago.get('realizado'):
        # Pago realizado pero no validado
        if not pago.get('validado'):
            return {
                'status': 'pending_validation',
                'emoji': '🟡',
                'text': 'Por validar',
                'color': 'yellow',
                'monto': pago.get('monto', 0),
                'medio': pago.get('medio', 'desconocido')
            }
        # Pago realizado y validado
        else:
            return {
                'status': 'paid',
                'emoji': '✅',
                'text': 'Pagado',
                'color': 'green',
                'monto': pago.get('monto', 0),
                'medio': pago.get('medio', 'desconocido')
            }
    else:
        # No se ha realizado el pago
        return {
            'status': 'pending',
            'emoji': '⚪',
            'text': 'Sin pago',
            'color': 'red'
        }


def determine_action(changes: Dict, stats: Dict) -> str:
    """Determinar acción sugerida basada en cambios y estadísticas"""

    if stats.get('critical', 0) > 0:
        return 'SHOW_URGENT_ALERT'
    elif changes.get('total_changes', 0) > 5:
        return 'SUGGEST_REFRESH'
    elif changes.get('new'):
        return 'SHOW_NEW_BADGE'
    elif changes.get('priority_changed'):
        return 'UPDATE_PRIORITIES'
    else:
        return 'NO_ACTION'
