"""
Service layer for servicio (services) management.
Handles transaction logic between MariaDB and Firestore.
"""

from typing import Dict, Any, Optional, List
from decimal import Decimal
from firebase_admin import firestore
import logging
import mysql.connector
from app.services.firestore_service import FirestoreService


logger = logging.getLogger(__name__)


class ServicioService:
    """Service for managing services with dual persistence (MariaDB + Firestore)"""

    def __init__(self, firestore_service: FirestoreService):
        self.firestore_service = firestore_service
        self.db = firestore_service.db

    def _normalize_service_name_for_firestore(self, nombre: str) -> str:
        """
        Convert service name to lowercase with underscores for Firestore key.

        Args:
            nombre: Service name (e.g., "Consulta General")

        Returns:
            Normalized name (e.g., "consulta_general")
        """
        # Replace spaces with underscores and convert to lowercase
        normalized = nombre.strip().lower().replace(' ', '_')
        # Remove special characters (keep only alphanumeric and underscores)
        normalized = ''.join(c if c.isalnum() or c == '_' else '_' for c in normalized)
        # Replace multiple consecutive underscores with single underscore
        while '__' in normalized:
            normalized = normalized.replace('__', '_')
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        return normalized

    async def sync_all_services_to_firestore(
        self,
        negocio_id: int,
        servicios: List[Dict[str, Any]]
    ) -> None:
        """
        Sync all services for a business to Firestore.
        Updates the 'precios_cita' field in the negocios collection.

        Args:
            negocio_id: Business ID
            servicios: List of service dictionaries with 'nombre' and 'precio'

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            # Build precios_cita dictionary
            precios_cita = {}
            for servicio in servicios:
                nombre = servicio.get('nombre', '')
                precio = servicio.get('precio', 0)

                # Convert to float if it's a Decimal
                if isinstance(precio, Decimal):
                    precio = float(precio)

                # Normalize service name for Firestore key
                key = self._normalize_service_name_for_firestore(nombre)
                precios_cita[key] = precio

            logger.info(f"Syncing {len(precios_cita)} services to Firestore for negocio_id {negocio_id}")

            # Update Firestore document in 'negocios' collection
            doc_ref = self.db.collection('negocios').document(str(negocio_id))

            # Use update() to REPLACE the entire precios_cita field
            # This ensures deleted services are removed from Firestore
            try:
                doc_ref.update({
                    'precios_cita': precios_cita,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                # If document doesn't exist, create it with set()
                if 'NOT_FOUND' in str(e) or 'not found' in str(e).lower():
                    logger.info(f"Document not found for negocio_id {negocio_id}, creating new document")
                    doc_ref.set({
                        'precios_cita': precios_cita,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                else:
                    raise

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for negocio_id {negocio_id}: {str(e)}")
            raise Exception(f"Error al sincronizar con Firestore: {str(e)}")

    async def create_servicio_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int,
        nombre: str,
        descripcion: Optional[str],
        duracion_minutos: int,
        precio: Decimal,
        activo: bool,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create service within an existing MariaDB transaction.
        This method is called by the endpoint after starting a transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            negocio_id: Business ID
            nombre: Service name
            descripcion: Service description
            duracion_minutos: Service duration
            precio: Service price
            activo: Service active status
            user_id: User ID

        Returns:
            Created service dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
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

            if not result:
                raise Exception("Failed to retrieve created service")

            # Convert tuple to dictionary (if cursor is not dictionary=True)
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            # Convert Decimal to float
            if result.get('precio') is not None:
                result['precio'] = float(result['precio'])

            logger.info(f"Service created in MariaDB: id={servicio_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error creating service in MariaDB: {str(e)}")
            raise

    async def update_servicio_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
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
        Update service within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            servicio_id: Service ID
            negocio_id: Business ID
            nombre: Service name (optional)
            descripcion: Service description (optional)
            duracion_minutos: Service duration (optional)
            precio: Service price (optional)
            activo: Service active status (optional)
            user_id: User ID

        Returns:
            Updated service dictionary or None if not found

        Raises:
            Exception: If database operation fails
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
                # No fields to update, just return current record
                cursor.execute(
                    """
                    SELECT
                        id, negocio_id, nombre, descripcion, duracion_minutos,
                        precio, activo, eliminado, created_at, updated_at,
                        created_by, updated_by
                    FROM servicios
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                    """,
                    (servicio_id, negocio_id)
                )
                result = cursor.fetchone()
            else:
                # Add WHERE clause parameters
                params.extend([servicio_id, negocio_id])

                query = f"""
                    UPDATE servicios
                    SET {', '.join(update_fields)}
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                """

                cursor.execute(query, params)
                rows_affected = cursor.rowcount

                if rows_affected == 0:
                    return None

                # Get the updated record
                cursor.execute(
                    """
                    SELECT
                        id, negocio_id, nombre, descripcion, duracion_minutos,
                        precio, activo, eliminado, created_at, updated_at,
                        created_by, updated_by
                    FROM servicios
                    WHERE id = %s
                    """,
                    (servicio_id,)
                )
                result = cursor.fetchone()

            if not result:
                return None

            # Convert tuple to dictionary
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            # Convert Decimal to float
            if result.get('precio') is not None:
                result['precio'] = float(result['precio'])

            logger.info(f"Service updated in MariaDB: id={servicio_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error updating service in MariaDB: {str(e)}")
            raise

    async def delete_servicio_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        servicio_id: int,
        negocio_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Soft delete service within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            servicio_id: Service ID
            negocio_id: Business ID
            user_id: User ID

        Returns:
            True if deleted, False if not found

        Raises:
            Exception: If database operation fails
        """
        try:
            cursor.execute(
                """
                UPDATE servicios
                SET eliminado = TRUE, updated_by = %s
                WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                """,
                (user_id, servicio_id, negocio_id)
            )
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                logger.info(f"Service soft deleted in MariaDB: id={servicio_id}, negocio_id={negocio_id}")
                return True
            else:
                logger.warning(f"Service not found for deletion: id={servicio_id}, negocio_id={negocio_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting service in MariaDB: {str(e)}")
            raise

    async def get_all_active_services(
        self,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all active services for Firestore sync.

        Args:
            cursor: Active database cursor
            negocio_id: Business ID

        Returns:
            List of active services
        """
        cursor.execute(
            """
            SELECT nombre, precio
            FROM servicios
            WHERE negocio_id = %s AND eliminado = FALSE
            ORDER BY nombre
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()

        # Convert to list of dictionaries
        services = []
        for row in results:
            if isinstance(row, tuple):
                services.append({
                    'nombre': row[0],
                    'precio': row[1]
                })
            else:
                services.append(row)

        return services

    def _get_db_config(self, key: str) -> str:
        """
        Get database configuration from settings.

        Args:
            key: Configuration key

        Returns:
            Configuration value
        """
        import os
        from app.config import settings

        # Try to get from settings first, fallback to environment variables
        value = getattr(settings, key, None)
        if value is None:
            value = os.getenv(key)

        if value is None:
            raise ValueError(f"Missing database configuration: {key}")

        return str(value)


# Dependency injection helper
def get_servicio_service(
    firestore_service: FirestoreService
) -> ServicioService:
    """FastAPI dependency for ServicioService"""
    return ServicioService(firestore_service)
