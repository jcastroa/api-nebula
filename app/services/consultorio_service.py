# app/services/consultorio_service.py
"""
Servicio para gestionar consultorios (negocios) en MariaDB
"""
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


class ConsultorioService:
    """Servicio para operaciones CRUD de consultorios en MariaDB"""

    @staticmethod
    def get_all_consultorios(
        search_term: Optional[str] = None,
        activo_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtener todos los consultorios con búsqueda opcional

        Args:
            search_term: Término de búsqueda (nombre o RUC)
            activo_only: Filtrar solo consultorios activos

        Returns:
            Lista de consultorios
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                # Construir query base
                query = """
                    SELECT
                        id,
                        nombre,
                        ruc,
                        direccion,
                        telefono,
                        email,
                        configuracion,
                        estado,
                        created_at,
                        updated_at,
                        es_principal
                    FROM consultorios
                    WHERE 1=1
                """
                params = []

                # Filtrar solo activos si se solicita
                if activo_only:
                    query += " AND estado = 'activo'"

                # Aplicar filtro de búsqueda
                if search_term:
                    query += " AND (nombre LIKE %s OR ruc LIKE %s OR email LIKE %s)"
                    search_pattern = f"%{search_term}%"
                    params.extend([search_pattern, search_pattern, search_pattern])

                # Ordenar por fecha de creación (más recientes primero)
                query += " ORDER BY created_at DESC"

                cursor.execute(query, params)
                consultorios = cursor.fetchall()

                # Parsear configuracion JSON
                for consultorio in consultorios:
                    if consultorio.get('configuracion'):
                        try:
                            consultorio['configuracion'] = json.loads(consultorio['configuracion'])
                        except json.JSONDecodeError:
                            consultorio['configuracion'] = {}
                    else:
                        consultorio['configuracion'] = {}

                    # Convertir datetime a string ISO
                    if consultorio.get('created_at'):
                        consultorio['created_at'] = consultorio['created_at'].isoformat()
                    if consultorio.get('updated_at'):
                        consultorio['updated_at'] = consultorio['updated_at'].isoformat()

                    # Mapear campos para compatibilidad con el schema
                    consultorio['activo'] = consultorio['estado'] == 'activo'
                    consultorio['telefono_contacto'] = consultorio.pop('telefono', None)
                    consultorio['nombre_responsable'] = consultorio['configuracion'].get('nombre_responsable')

                    # Extraer campos de configuracion
                    config = consultorio['configuracion']
                    consultorio['permite_pago'] = config.get('permite_pago', False)
                    consultorio['envia_recordatorios'] = config.get('envia_recordatorios', False)
                    consultorio['con_confirmacion_cita'] = config.get('con_confirmacion_cita', False)

                cursor.close()
                logger.info(f"Retrieved {len(consultorios)} consultorios")
                return consultorios

        except Exception as e:
            logger.error(f"Error getting consultorios: {e}")
            raise

    @staticmethod
    def get_consultorio_by_id(consultorio_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtener consultorio por ID

        Args:
            consultorio_id: ID del consultorio

        Returns:
            Datos del consultorio o None si no existe
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                query = """
                    SELECT
                        id,
                        nombre,
                        ruc,
                        direccion,
                        telefono,
                        email,
                        configuracion,
                        estado,
                        created_at,
                        updated_at,
                        es_principal
                    FROM consultorios
                    WHERE id = %s
                """

                cursor.execute(query, (consultorio_id,))
                consultorio = cursor.fetchone()
                cursor.close()

                if not consultorio:
                    return None

                # Parsear configuracion JSON
                if consultorio.get('configuracion'):
                    try:
                        consultorio['configuracion'] = json.loads(consultorio['configuracion'])
                    except json.JSONDecodeError:
                        consultorio['configuracion'] = {}
                else:
                    consultorio['configuracion'] = {}

                # Convertir datetime a string ISO
                if consultorio.get('created_at'):
                    consultorio['created_at'] = consultorio['created_at'].isoformat()
                if consultorio.get('updated_at'):
                    consultorio['updated_at'] = consultorio['updated_at'].isoformat()

                # Mapear campos
                consultorio['activo'] = consultorio['estado'] == 'activo'
                consultorio['telefono_contacto'] = consultorio.pop('telefono', None)
                consultorio['nombre_responsable'] = consultorio['configuracion'].get('nombre_responsable')

                # Extraer campos de configuracion
                config = consultorio['configuracion']
                consultorio['permite_pago'] = config.get('permite_pago', False)
                consultorio['envia_recordatorios'] = config.get('envia_recordatorios', False)
                consultorio['con_confirmacion_cita'] = config.get('con_confirmacion_cita', False)

                return consultorio

        except Exception as e:
            logger.error(f"Error getting consultorio {consultorio_id}: {e}")
            raise

    @staticmethod
    def create_consultorio(consultorio_data: Dict[str, Any]) -> int:
        """
        Crear nuevo consultorio

        Args:
            consultorio_data: Datos del consultorio

        Returns:
            ID del consultorio creado
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Preparar configuracion JSON
                configuracion = {
                    'permite_pago': consultorio_data.get('permite_pago', False),
                    'envia_recordatorios': consultorio_data.get('envia_recordatorios', False),
                    'con_confirmacion_cita': consultorio_data.get('con_confirmacion_cita', False),
                    'nombre_responsable': consultorio_data.get('nombre_responsable')
                }

                # Determinar estado basado en activo
                estado = 'activo' if consultorio_data.get('activo', True) else 'inactivo'

                query = """
                    INSERT INTO consultorios
                    (nombre, ruc, direccion, telefono, email, configuracion, estado, es_principal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """

                params = (
                    consultorio_data.get('nombre'),
                    consultorio_data.get('ruc'),
                    consultorio_data.get('direccion'),
                    consultorio_data.get('telefono_contacto'),
                    consultorio_data.get('email'),
                    json.dumps(configuracion),
                    estado,
                    consultorio_data.get('es_principal', False)
                )

                cursor.execute(query, params)
                consultorio_id = cursor.lastrowid
                conn.commit()
                cursor.close()

                logger.info(f"Consultorio created with ID: {consultorio_id}")
                return consultorio_id

        except Exception as e:
            logger.error(f"Error creating consultorio: {e}")
            raise

    @staticmethod
    def update_consultorio(
        consultorio_id: int,
        update_data: Dict[str, Any]
    ) -> bool:
        """
        Actualizar consultorio existente

        Args:
            consultorio_id: ID del consultorio
            update_data: Datos a actualizar

        Returns:
            True si se actualizó correctamente
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                # Verificar que el consultorio existe
                cursor.execute("SELECT id, configuracion FROM consultorios WHERE id = %s", (consultorio_id,))
                consultorio = cursor.fetchone()

                if not consultorio:
                    logger.warning(f"Consultorio {consultorio_id} not found")
                    return False

                # Parsear configuracion existente
                try:
                    configuracion = json.loads(consultorio['configuracion']) if consultorio['configuracion'] else {}
                except json.JSONDecodeError:
                    configuracion = {}

                # Construir query de actualización dinámicamente
                update_fields = []
                params = []

                # Campos directos
                if 'nombre' in update_data:
                    update_fields.append("nombre = %s")
                    params.append(update_data['nombre'])

                if 'ruc' in update_data:
                    update_fields.append("ruc = %s")
                    params.append(update_data['ruc'])

                if 'direccion' in update_data:
                    update_fields.append("direccion = %s")
                    params.append(update_data['direccion'])

                if 'telefono_contacto' in update_data:
                    update_fields.append("telefono = %s")
                    params.append(update_data['telefono_contacto'])

                if 'email' in update_data:
                    update_fields.append("email = %s")
                    params.append(update_data['email'])

                if 'es_principal' in update_data:
                    update_fields.append("es_principal = %s")
                    params.append(update_data['es_principal'])

                # Actualizar estado si activo está presente
                if 'activo' in update_data:
                    estado = 'activo' if update_data['activo'] else 'inactivo'
                    update_fields.append("estado = %s")
                    params.append(estado)

                # Actualizar campos en configuracion
                config_updated = False
                if 'permite_pago' in update_data:
                    configuracion['permite_pago'] = update_data['permite_pago']
                    config_updated = True

                if 'envia_recordatorios' in update_data:
                    configuracion['envia_recordatorios'] = update_data['envia_recordatorios']
                    config_updated = True

                if 'con_confirmacion_cita' in update_data:
                    configuracion['con_confirmacion_cita'] = update_data['con_confirmacion_cita']
                    config_updated = True

                if 'nombre_responsable' in update_data:
                    configuracion['nombre_responsable'] = update_data['nombre_responsable']
                    config_updated = True

                if config_updated:
                    update_fields.append("configuracion = %s")
                    params.append(json.dumps(configuracion))

                if not update_fields:
                    logger.warning("No fields to update")
                    return False

                # Construir y ejecutar query
                query = f"UPDATE consultorios SET {', '.join(update_fields)} WHERE id = %s"
                params.append(consultorio_id)

                cursor.execute(query, params)
                conn.commit()
                cursor.close()

                logger.info(f"Consultorio {consultorio_id} updated successfully")
                return True

        except Exception as e:
            logger.error(f"Error updating consultorio {consultorio_id}: {e}")
            raise

    @staticmethod
    def cambiar_estado_consultorio(
        consultorio_id: int,
        activo: bool
    ) -> bool:
        """
        Cambiar estado activo/inactivo de un consultorio

        Args:
            consultorio_id: ID del consultorio
            activo: Nuevo estado

        Returns:
            True si se actualizó correctamente
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Verificar que el consultorio existe
                cursor.execute("SELECT id FROM consultorios WHERE id = %s", (consultorio_id,))
                if not cursor.fetchone():
                    logger.warning(f"Consultorio {consultorio_id} not found")
                    return False

                # Actualizar estado
                estado = 'activo' if activo else 'inactivo'
                query = "UPDATE consultorios SET estado = %s WHERE id = %s"

                cursor.execute(query, (estado, consultorio_id))
                conn.commit()
                cursor.close()

                logger.info(f"Consultorio {consultorio_id} estado changed to {estado}")
                return True

        except Exception as e:
            logger.error(f"Error changing estado for consultorio {consultorio_id}: {e}")
            raise

    @staticmethod
    def verificar_existe_en_firestore(consultorio_id: int, firestore_service) -> bool:
        """
        Verificar si el consultorio existe también en Firestore

        Args:
            consultorio_id: ID del consultorio
            firestore_service: Instancia del servicio de Firestore

        Returns:
            True si existe en Firestore
        """
        try:
            # Buscar por el ID como string en Firestore
            doc_ref = firestore_service.db.collection("negocios").document(str(consultorio_id))
            doc = doc_ref.get()
            return doc.exists
        except Exception as e:
            logger.warning(f"Error verificando existencia en Firestore: {e}")
            return False
