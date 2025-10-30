# ==========================================
# app/crud/assignment.py - CRUD de asignaciones
# ==========================================

"""CRUD operations para la tabla usuario_consultorios"""
from typing import Optional, List, Dict, Any
from app.crud.base import BaseCRUD
from app.core.database import get_db_connection
import logging

logger = logging.getLogger(__name__)

class AssignmentCRUD(BaseCRUD):
    """CRUD específico para asignaciones de usuarios a consultorios"""

    def __init__(self):
        super().__init__(None)  # No usamos modelo ORM

    async def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Obtener asignación por ID"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT
                        uc.id,
                        uc.usuario_id,
                        uc.consultorio_id,
                        c.nombre as consultorio_nombre,
                        uc.rol_id,
                        r.nombre as rol_nombre,
                        uc.es_principal,
                        uc.estado,
                        uc.fecha_asignacion,
                        uc.fecha_inicio,
                        uc.fecha_fin,
                        uc.created_at,
                        uc.updated_at
                    FROM usuario_consultorios uc
                    INNER JOIN consultorios c ON uc.consultorio_id = c.id
                    INNER JOIN roles r ON uc.rol_id = r.id_rol
                    WHERE uc.id = %s
                """, (id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting assignment {id}: {e}")
            return None

    async def get_by_user(self, usuario_id: int) -> List[Dict[str, Any]]:
        """Obtener todas las asignaciones de un usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT
                        uc.id,
                        uc.usuario_id,
                        uc.consultorio_id,
                        c.nombre as consultorio_nombre,
                        uc.rol_id,
                        r.nombre as rol_nombre,
                        uc.es_principal,
                        uc.estado,
                        uc.fecha_asignacion,
                        uc.fecha_inicio,
                        uc.fecha_fin,
                        uc.created_at,
                        uc.updated_at
                    FROM usuario_consultorios uc
                    INNER JOIN consultorios c ON uc.consultorio_id = c.id
                    INNER JOIN roles r ON uc.rol_id = r.id_rol
                    WHERE uc.usuario_id = %s
                    ORDER BY uc.es_principal DESC, c.nombre
                """, (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting assignments for user {usuario_id}: {e}")
            return []

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Obtener múltiples asignaciones con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                # Query base
                query = """
                    SELECT
                        uc.id,
                        uc.usuario_id,
                        uc.consultorio_id,
                        c.nombre as consultorio_nombre,
                        uc.rol_id,
                        r.nombre as rol_nombre,
                        uc.es_principal,
                        uc.estado,
                        uc.fecha_asignacion,
                        uc.fecha_inicio,
                        uc.fecha_fin,
                        uc.created_at,
                        uc.updated_at
                    FROM usuario_consultorios uc
                    INNER JOIN consultorios c ON uc.consultorio_id = c.id
                    INNER JOIN roles r ON uc.rol_id = r.id_rol
                    WHERE 1=1
                """
                params = []

                # Aplicar filtros
                if filters:
                    if filters.get('usuario_id'):
                        query += " AND uc.usuario_id = %s"
                        params.append(filters['usuario_id'])

                    if filters.get('negocio_id'):
                        query += " AND uc.consultorio_id = %s"
                        params.append(filters['negocio_id'])

                    if filters.get('estado'):
                        query += " AND uc.estado = %s"
                        params.append(filters['estado'])

                # Ordenar y paginar
                query += " ORDER BY uc.created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, skip])

                cursor.execute(query, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error getting assignments: {e}")
            return []

    async def create(self, obj_in: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear nueva asignación"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)

                # Verificar si el usuario ya está asignado a este consultorio
                cursor.execute("""
                    SELECT id FROM usuario_consultorios
                    WHERE usuario_id = %s AND consultorio_id = %s
                """, (obj_in['usuario_id'], obj_in['negocio_id']))

                existing = cursor.fetchone()
                if existing:
                    logger.warning(f"User {obj_in['usuario_id']} already assigned to consultorio {obj_in['negocio_id']}")
                    return None

                # Si es_principal=True, desmarcar otras asignaciones principales del usuario
                if obj_in.get('es_principal', False):
                    cursor.execute("""
                        UPDATE usuario_consultorios
                        SET es_principal = FALSE
                        WHERE usuario_id = %s AND es_principal = TRUE
                    """, (obj_in['usuario_id'],))

                # Insertar asignación
                cursor.execute("""
                    INSERT INTO usuario_consultorios
                    (usuario_id, consultorio_id, rol_id, es_principal, fecha_inicio, fecha_fin)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    obj_in['usuario_id'],
                    obj_in['negocio_id'],
                    obj_in['rol_id'],
                    obj_in.get('es_principal', False),
                    obj_in.get('fecha_inicio'),
                    obj_in.get('fecha_fin')
                ))

                assignment_id = cursor.lastrowid
                conn.commit()

                # Retornar la asignación creada
                return await self.get(assignment_id)

        except Exception as e:
            logger.error(f"Error creating assignment: {e}")
            return None

    async def update(
        self,
        id: int,
        obj_in: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Actualizar asignación existente"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)

                # Obtener la asignación actual
                assignment = await self.get(id)
                if not assignment:
                    return None

                # Si es_principal=True, desmarcar otras asignaciones principales del usuario
                if obj_in.get('es_principal', False):
                    cursor.execute("""
                        UPDATE usuario_consultorios
                        SET es_principal = FALSE
                        WHERE usuario_id = %s AND es_principal = TRUE AND id != %s
                    """, (assignment['usuario_id'], id))

                # Construir query dinámicamente
                fields = []
                params = []

                # Campos actualizables
                updateable_fields = ['rol_id', 'es_principal', 'fecha_inicio', 'fecha_fin']

                for field in updateable_fields:
                    if field in obj_in and obj_in[field] is not None:
                        fields.append(f"{field} = %s")
                        params.append(obj_in[field])

                if not fields:
                    # No hay campos para actualizar
                    return await self.get(id)

                # Actualizar timestamp
                fields.append("updated_at = CURRENT_TIMESTAMP")

                # Ejecutar update
                query = f"UPDATE usuario_consultorios SET {', '.join(fields)} WHERE id = %s"
                params.append(id)

                cursor.execute(query, params)
                conn.commit()

                if cursor.rowcount > 0:
                    return await self.get(id)

                return None

        except Exception as e:
            logger.error(f"Error updating assignment {id}: {e}")
            return None

    async def delete(self, id: int) -> bool:
        """Eliminar asignación (hard delete)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                cursor.execute("""
                    DELETE FROM usuario_consultorios
                    WHERE id = %s
                """, (id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting assignment {id}: {e}")
            return False

    async def activate(self, id: int) -> Optional[Dict[str, Any]]:
        """Activar asignación"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                cursor.execute("""
                    UPDATE usuario_consultorios
                    SET estado = 'activo', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
                conn.commit()

                if cursor.rowcount > 0:
                    return await self.get(id)

                return None
        except Exception as e:
            logger.error(f"Error activating assignment {id}: {e}")
            return None

    async def deactivate(self, id: int) -> Optional[Dict[str, Any]]:
        """Desactivar asignación"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                cursor.execute("""
                    UPDATE usuario_consultorios
                    SET estado = 'inactivo', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
                conn.commit()

                if cursor.rowcount > 0:
                    return await self.get(id)

                return None
        except Exception as e:
            logger.error(f"Error deactivating assignment {id}: {e}")
            return None

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Contar asignaciones con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)

                query = "SELECT COUNT(*) as total FROM usuario_consultorios uc WHERE 1=1"
                params = []

                if filters:
                    if filters.get('usuario_id'):
                        query += " AND uc.usuario_id = %s"
                        params.append(filters['usuario_id'])

                    if filters.get('negocio_id'):
                        query += " AND uc.consultorio_id = %s"
                        params.append(filters['negocio_id'])

                    if filters.get('estado'):
                        query += " AND uc.estado = %s"
                        params.append(filters['estado'])

                cursor.execute(query, params)
                result = cursor.fetchone()
                return result['total'] if result else 0

        except Exception as e:
            logger.error(f"Error counting assignments: {e}")
            return 0
