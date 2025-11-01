"""
Service layer for promocion (promotions) management.
Handles transaction logic between MariaDB and Firestore.
"""

from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import date
from firebase_admin import firestore
import logging
import mysql.connector
from app.services.firestore_service import FirestoreService


logger = logging.getLogger(__name__)


class PromocionService:
    """Service for managing promotions with dual persistence (MariaDB + Firestore)"""

    def __init__(self, firestore_service: FirestoreService):
        self.firestore_service = firestore_service
        self.db = firestore_service.db

    async def sync_promocion_to_firestore(
        self,
        promocion: Dict[str, Any]
    ) -> None:
        """
        Sync a single promotion to Firestore.
        Stores in 'promociones' collection with promocion ID as document ID.

        Args:
            promocion: Promotion dictionary with all fields

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            promocion_id = promocion.get('id')
            if not promocion_id:
                raise ValueError("Promotion ID is required for Firestore sync")

            # Convert Decimal to float for Firestore
            valor_descuento = promocion.get('valor_descuento', 0)
            if isinstance(valor_descuento, Decimal):
                valor_descuento = float(valor_descuento)

            # Convert date to string for Firestore
            fecha_inicio = promocion.get('fecha_inicio')
            if isinstance(fecha_inicio, date):
                fecha_inicio = fecha_inicio.isoformat()

            fecha_fin = promocion.get('fecha_fin')
            if isinstance(fecha_fin, date):
                fecha_fin = fecha_fin.isoformat()

            # Prepare document data
            doc_data = {
                'id': promocion_id,
                'negocio_id': promocion.get('negocio_id'),
                'titulo': promocion.get('titulo', ''),
                'descripcion': promocion.get('descripcion', ''),
                'tipo_descuento': promocion.get('tipo_descuento', 'porcentaje'),
                'valor_descuento': valor_descuento,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'activo': promocion.get('activo', True),
                'updated_at': firestore.SERVER_TIMESTAMP
            }

            logger.info(f"Syncing promotion {promocion_id} to Firestore")

            # Update Firestore document in 'promociones' collection
            # Use promocion_id as the document ID
            doc_ref = self.db.collection('promociones').document(str(promocion_id))
            doc_ref.set(doc_data, merge=True)

            logger.info(f"Firestore sync successful for promocion_id {promocion_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for promocion: {str(e)}")
            raise Exception(f"Error al sincronizar con Firestore: {str(e)}")

    async def delete_promocion_from_firestore(
        self,
        promocion_id: int
    ) -> None:
        """
        Delete a promotion from Firestore.

        Args:
            promocion_id: Promotion ID

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            logger.info(f"Deleting promotion {promocion_id} from Firestore")

            # Delete Firestore document
            doc_ref = self.db.collection('promociones').document(str(promocion_id))
            doc_ref.delete()

            logger.info(f"Firestore delete successful for promocion_id {promocion_id}")

        except Exception as e:
            logger.error(f"Firestore delete failed for promocion {promocion_id}: {str(e)}")
            raise Exception(f"Error al eliminar de Firestore: {str(e)}")

    async def create_promocion_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int,
        titulo: str,
        descripcion: str,
        tipo_descuento: str,
        valor_descuento: Decimal,
        fecha_inicio: date,
        fecha_fin: date,
        activo: bool,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create promotion within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            negocio_id: Business ID
            titulo: Promotion title
            descripcion: Promotion description
            tipo_descuento: Discount type ('porcentaje' or 'monto_fijo')
            valor_descuento: Discount value
            fecha_inicio: Start date
            fecha_fin: End date
            activo: Active status
            user_id: User ID

        Returns:
            Created promotion dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            # Convert Decimal to float to ensure proper precision in MariaDB
            valor_descuento_float = float(valor_descuento) if isinstance(valor_descuento, Decimal) else valor_descuento

            cursor.execute(
                """
                INSERT INTO promociones
                    (negocio_id, titulo, descripcion, tipo_descuento, valor_descuento,
                     fecha_inicio, fecha_fin, activo, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (negocio_id, titulo, descripcion, tipo_descuento, valor_descuento_float,
                 fecha_inicio, fecha_fin, activo, user_id)
            )

            promocion_id = cursor.lastrowid

            # Get the created record
            cursor.execute(
                """
                SELECT
                    id,
                    negocio_id,
                    titulo,
                    descripcion,
                    tipo_descuento,
                    valor_descuento,
                    fecha_inicio,
                    fecha_fin,
                    activo,
                    eliminado,
                    created_at,
                    updated_at,
                    created_by,
                    updated_by
                FROM promociones
                WHERE id = %s
                """,
                (promocion_id,)
            )
            result = cursor.fetchone()

            if not result:
                raise Exception("Failed to retrieve created promotion")

            # Convert tuple to dictionary (if cursor is not dictionary=True)
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            # Convert Decimal to float
            if result.get('valor_descuento') is not None:
                result['valor_descuento'] = float(result['valor_descuento'])

            logger.info(f"Promotion created in MariaDB: id={promocion_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error creating promotion in MariaDB: {str(e)}")
            raise

    async def update_promocion_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        promocion_id: int,
        negocio_id: int,
        titulo: Optional[str] = None,
        descripcion: Optional[str] = None,
        tipo_descuento: Optional[str] = None,
        valor_descuento: Optional[Decimal] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        activo: Optional[bool] = None,
        user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update promotion within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            promocion_id: Promotion ID
            negocio_id: Business ID
            titulo: Promotion title (optional)
            descripcion: Promotion description (optional)
            tipo_descuento: Discount type (optional)
            valor_descuento: Discount value (optional)
            fecha_inicio: Start date (optional)
            fecha_fin: End date (optional)
            activo: Active status (optional)
            user_id: User ID

        Returns:
            Updated promotion dictionary or None if not found

        Raises:
            Exception: If database operation fails
        """
        try:
            # Build dynamic update query
            update_fields = []
            params = []

            if titulo is not None:
                update_fields.append("titulo = %s")
                params.append(titulo)

            if descripcion is not None:
                update_fields.append("descripcion = %s")
                params.append(descripcion)

            if tipo_descuento is not None:
                update_fields.append("tipo_descuento = %s")
                params.append(tipo_descuento)

            if valor_descuento is not None:
                update_fields.append("valor_descuento = %s")
                # Convert Decimal to float to ensure proper precision
                valor_descuento_float = float(valor_descuento) if isinstance(valor_descuento, Decimal) else valor_descuento
                params.append(valor_descuento_float)

            if fecha_inicio is not None:
                update_fields.append("fecha_inicio = %s")
                params.append(fecha_inicio)

            if fecha_fin is not None:
                update_fields.append("fecha_fin = %s")
                params.append(fecha_fin)

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
                        id, negocio_id, titulo, descripcion, tipo_descuento,
                        valor_descuento, fecha_inicio, fecha_fin, activo, eliminado,
                        created_at, updated_at, created_by, updated_by
                    FROM promociones
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                    """,
                    (promocion_id, negocio_id)
                )
                result = cursor.fetchone()
            else:
                # Add WHERE clause parameters
                params.extend([promocion_id, negocio_id])

                query = f"""
                    UPDATE promociones
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
                        id, negocio_id, titulo, descripcion, tipo_descuento,
                        valor_descuento, fecha_inicio, fecha_fin, activo, eliminado,
                        created_at, updated_at, created_by, updated_by
                    FROM promociones
                    WHERE id = %s
                    """,
                    (promocion_id,)
                )
                result = cursor.fetchone()

            if not result:
                return None

            # Convert tuple to dictionary
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            # Convert Decimal to float
            if result.get('valor_descuento') is not None:
                result['valor_descuento'] = float(result['valor_descuento'])

            logger.info(f"Promotion updated in MariaDB: id={promocion_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error updating promotion in MariaDB: {str(e)}")
            raise

    async def delete_promocion_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        promocion_id: int,
        negocio_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Soft delete promotion within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            promocion_id: Promotion ID
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
                UPDATE promociones
                SET eliminado = TRUE, updated_by = %s
                WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                """,
                (user_id, promocion_id, negocio_id)
            )
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                logger.info(f"Promotion soft deleted in MariaDB: id={promocion_id}, negocio_id={negocio_id}")
                return True
            else:
                logger.warning(f"Promotion not found for deletion: id={promocion_id}, negocio_id={negocio_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting promotion in MariaDB: {str(e)}")
            raise


# Dependency injection helper
def get_promocion_service(
    firestore_service: FirestoreService
) -> PromocionService:
    """FastAPI dependency for PromocionService"""
    return PromocionService(firestore_service)
