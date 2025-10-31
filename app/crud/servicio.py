"""
CRUD operations for servicios table.
Handles database operations for services management.
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from app.core.database import get_db_connection
from app.core.logging import logger


class ServicioCRUD:
    """CRUD operations for services"""

    async def get_all_by_negocio_id(self, negocio_id: int) -> List[Dict[str, Any]]:
        """
        Get all active (non-deleted) services for a business.

        Args:
            negocio_id: Business ID

        Returns:
            List of service dictionaries
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT
                        id,
                        negocio_id,
                        nombre,
                        descripcion,
                        duracion_minutos,
                        precio,
                        activo,
                        eliminado,
                        created_at,
                        updated_at,
                        created_by,
                        updated_by
                    FROM servicios
                    WHERE negocio_id = %s AND eliminado = FALSE
                    ORDER BY created_at DESC
                    """,
                    (negocio_id,)
                )
                results = cursor.fetchall()
                cursor.close()

                # Convert Decimal to float for JSON serialization
                for row in results:
                    if row.get('precio') is not None:
                        row['precio'] = float(row['precio'])

                return results

        except Exception as e:
            logger.error(f"Error getting services for negocio_id {negocio_id}: {str(e)}")
            raise

    async def get_by_id(self, servicio_id: int, negocio_id: int) -> Optional[Dict[str, Any]]:
        """
        Get service by ID and negocio_id.

        Args:
            servicio_id: Service ID
            negocio_id: Business ID

        Returns:
            Service dictionary or None if not found
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT
                        id,
                        negocio_id,
                        nombre,
                        descripcion,
                        duracion_minutos,
                        precio,
                        activo,
                        eliminado,
                        created_at,
                        updated_at,
                        created_by,
                        updated_by
                    FROM servicios
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                    """,
                    (servicio_id, negocio_id)
                )
                result = cursor.fetchone()
                cursor.close()

                # Convert Decimal to float
                if result and result.get('precio') is not None:
                    result['precio'] = float(result['precio'])

                return result

        except Exception as e:
            logger.error(f"Error getting service {servicio_id}: {str(e)}")
            raise

    async def create(
        self,
        negocio_id: int,
        nombre: str,
        descripcion: Optional[str],
        duracion_minutos: int,
        precio: Decimal,
        activo: bool,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new service.

        Args:
            negocio_id: Business ID
            nombre: Service name
            descripcion: Service description
            duracion_minutos: Service duration in minutes
            precio: Service price
            activo: Service active status
            user_id: User ID who creates the service

        Returns:
            Created service dictionary
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                cursor.execute(
                    """
                    INSERT INTO servicios
                        (negocio_id, nombre, descripcion, duracion_minutos, precio, activo, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (negocio_id, nombre, descripcion, duracion_minutos, precio, activo, user_id)
                )

                servicio_id = cursor.lastrowid

                # Get the created record
                cursor.execute(
                    """
                    SELECT
                        id,
                        negocio_id,
                        nombre,
                        descripcion,
                        duracion_minutos,
                        precio,
                        activo,
                        eliminado,
                        created_at,
                        updated_at,
                        created_by,
                        updated_by
                    FROM servicios
                    WHERE id = %s
                    """,
                    (servicio_id,)
                )
                result = cursor.fetchone()
                cursor.close()

                if not result:
                    raise Exception("Failed to retrieve created service")

                # Convert Decimal to float
                if result.get('precio') is not None:
                    result['precio'] = float(result['precio'])

                return result

        except Exception as e:
            logger.error(f"Error creating service for negocio_id {negocio_id}: {str(e)}")
            raise

    async def update(
        self,
        servicio_id: int,
        negocio_id: int,
        nombre: Optional[str] = None,
        descripcion: Optional[str] = None,
        duracion_minutos: Optional[int] = None,
        precio: Optional[Decimal] = None,
        activo: Optional[bool] = None,
        user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing service.

        Args:
            servicio_id: Service ID
            negocio_id: Business ID
            nombre: Service name (optional)
            descripcion: Service description (optional)
            duracion_minutos: Service duration (optional)
            precio: Service price (optional)
            activo: Service active status (optional)
            user_id: User ID who updates the service

        Returns:
            Updated service dictionary or None if not found
        """
        try:
            # Build dynamic update query
            update_fields = []
            params = []

            if nombre is not None:
                update_fields.append("nombre = %s")
                params.append(nombre)

            if descripcion is not None:
                update_fields.append("descripcion = %s")
                params.append(descripcion)

            if duracion_minutos is not None:
                update_fields.append("duracion_minutos = %s")
                params.append(duracion_minutos)

            if precio is not None:
                update_fields.append("precio = %s")
                params.append(precio)

            if activo is not None:
                update_fields.append("activo = %s")
                params.append(activo)

            # Always update updated_by
            update_fields.append("updated_by = %s")
            params.append(user_id)

            if not update_fields:
                # No fields to update
                return await self.get_by_id(servicio_id, negocio_id)

            # Add WHERE clause parameters
            params.extend([servicio_id, negocio_id])

            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)

                query = f"""
                    UPDATE servicios
                    SET {', '.join(update_fields)}
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                """

                cursor.execute(query, params)
                rows_affected = cursor.rowcount

                if rows_affected == 0:
                    cursor.close()
                    return None

                # Get the updated record
                cursor.execute(
                    """
                    SELECT
                        id,
                        negocio_id,
                        nombre,
                        descripcion,
                        duracion_minutos,
                        precio,
                        activo,
                        eliminado,
                        created_at,
                        updated_at,
                        created_by,
                        updated_by
                    FROM servicios
                    WHERE id = %s
                    """,
                    (servicio_id,)
                )
                result = cursor.fetchone()
                cursor.close()

                # Convert Decimal to float
                if result and result.get('precio') is not None:
                    result['precio'] = float(result['precio'])

                return result

        except Exception as e:
            logger.error(f"Error updating service {servicio_id}: {str(e)}")
            raise

    async def soft_delete(
        self,
        servicio_id: int,
        negocio_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Soft delete a service (set eliminado = TRUE).

        Args:
            servicio_id: Service ID
            negocio_id: Business ID
            user_id: User ID who deletes the service

        Returns:
            True if deleted, False if not found
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE servicios
                    SET eliminado = TRUE, updated_by = %s
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                    """,
                    (user_id, servicio_id, negocio_id)
                )
                rows_affected = cursor.rowcount
                cursor.close()

                return rows_affected > 0

        except Exception as e:
            logger.error(f"Error soft deleting service {servicio_id}: {str(e)}")
            raise


# Dependency injection helper
def get_servicio_crud() -> ServicioCRUD:
    """FastAPI dependency for ServicioCRUD"""
    return ServicioCRUD()
