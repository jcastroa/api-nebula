# ==========================================
# app/crud/role.py - CRUD de roles
# ==========================================

"""CRUD operations para la tabla roles"""
from typing import Optional, List, Dict, Any
from app.crud.base import BaseCRUD
from app.core.database import get_db_connection
import logging

logger = logging.getLogger(__name__)

class RoleCRUD(BaseCRUD):
    """CRUD específico para roles"""

    def __init__(self):
        super().__init__(None)  # No usamos modelo ORM

    async def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Obtener rol por ID"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id_rol, nombre, descripcion, activo, fecha_creacion,
                           creado_por, modificado_por, fecha_modificacion
                    FROM roles
                    WHERE id_rol = %s
                """, (id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting role {id}: {e}")
            return None

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Obtener múltiples roles con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                # Query base
                query = """
                    SELECT id_rol, nombre, descripcion, activo, fecha_creacion,
                           creado_por, modificado_por, fecha_modificacion
                    FROM roles
                    WHERE 1=1
                """
                params = []

                # Aplicar filtros
                if filters:
                    if filters.get('activo') is not None:
                        query += " AND activo = %s"
                        params.append(filters['activo'])

                    if filters.get('search'):
                        search_term = f"%{filters['search']}%"
                        query += " AND (nombre LIKE %s OR descripcion LIKE %s)"
                        params.extend([search_term, search_term])

                # Ordenar y paginar
                query += " ORDER BY nombre LIMIT %s OFFSET %s"
                params.extend([limit, skip])

                cursor.execute(query, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error getting roles: {e}")
            return []

    async def get_all_active(self) -> List[Dict[str, Any]]:
        """Obtener todos los roles activos"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id_rol, nombre, descripcion, activo, fecha_creacion
                    FROM roles
                    WHERE activo = 1
                    ORDER BY nombre
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting active roles: {e}")
            return []

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Contar roles con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)

                query = "SELECT COUNT(*) as total FROM roles WHERE 1=1"
                params = []

                if filters:
                    if filters.get('activo') is not None:
                        query += " AND activo = %s"
                        params.append(filters['activo'])

                    if filters.get('search'):
                        search_term = f"%{filters['search']}%"
                        query += " AND (nombre LIKE %s OR descripcion LIKE %s)"
                        params.extend([search_term, search_term])

                cursor.execute(query, params)
                result = cursor.fetchone()
                return result['total'] if result else 0

        except Exception as e:
            logger.error(f"Error counting roles: {e}")
            return 0
