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

    async def sync_all_promociones_to_firestore(
        self,
        negocio_id: int,
        promociones: List[Dict[str, Any]]
    ) -> None:
        """
        Sync all promotions for a business to Firestore.
        Updates the 'promociones' array in the negocios collection.

        Args:
            negocio_id: Business ID
            promociones: List of promotion dictionaries

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            # Build promociones array for Firestore
            promociones_array = []
            for promo in promociones:
                # Convert Decimal to float for Firestore
                valor_descuento = promo.get('valor_descuento', 0)
                if isinstance(valor_descuento, Decimal):
                    valor_descuento = float(valor_descuento)

                # Convert date to string for Firestore
                fecha_inicio = promo.get('fecha_inicio')
                if isinstance(fecha_inicio, date):
                    fecha_inicio = fecha_inicio.isoformat()

                fecha_fin = promo.get('fecha_fin')
                if isinstance(fecha_fin, date):
                    fecha_fin = fecha_fin.isoformat()

                promociones_array.append({
                    'id': promo.get('id'),
                    'titulo': promo.get('titulo', ''),
                    'descripcion': promo.get('descripcion', ''),
                    'tipo_descuento': promo.get('tipo_descuento', 'porcentaje'),
                    'valor_descuento': valor_descuento,
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin,
                    'activo': promo.get('activo', True)
                })

            logger.info(f"Syncing {len(promociones_array)} promotions to Firestore for negocio_id {negocio_id}")

            # Update Firestore document in 'negocios' collection
            doc_ref = self.db.collection('negocios').document(str(negocio_id))

            # Use update() to REPLACE the entire promociones array
            # This ensures deleted promotions are removed from Firestore
            try:
                doc_ref.update({
                    'promociones': promociones_array,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                # If document doesn't exist, create it with set()
                if 'NOT_FOUND' in str(e) or 'not found' in str(e).lower():
                    logger.info(f"Document not found for negocio_id {negocio_id}, creating new document")
                    doc_ref.set({
                        'promociones': promociones_array,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                else:
                    raise

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for negocio_id {negocio_id}: {str(e)}")
            raise Exception(f"Error al sincronizar con Firestore: {str(e)}")

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
            cursor.execute(
                """
                INSERT INTO promociones
                    (negocio_id, titulo, descripcion, tipo_descuento, valor_descuento,
                     fecha_inicio, fecha_fin, activo, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (negocio_id, titulo, descripcion, tipo_descuento, valor_descuento,
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
                params.append(valor_descuento)

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

    async def get_all_active_promociones(
        self,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all active promotions for Firestore sync.

        Args:
            cursor: Active database cursor
            negocio_id: Business ID

        Returns:
            List of active promotions
        """
        cursor.execute(
            """
            SELECT
                id, titulo, descripcion, tipo_descuento, valor_descuento,
                fecha_inicio, fecha_fin, activo
            FROM promociones
            WHERE negocio_id = %s AND eliminado = FALSE AND activo = TRUE
            ORDER BY fecha_inicio DESC
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()

        # Convert to list of dictionaries
        promociones = []
        for row in results:
            if isinstance(row, tuple):
                promociones.append({
                    'id': row[0],
                    'titulo': row[1],
                    'descripcion': row[2],
                    'tipo_descuento': row[3],
                    'valor_descuento': row[4],
                    'fecha_inicio': row[5],
                    'fecha_fin': row[6],
                    'activo': row[7]
                })
            else:
                promociones.append(row)

        return promociones


# Dependency injection helper
def get_promocion_service(
    firestore_service: FirestoreService
) -> PromocionService:
    """FastAPI dependency for PromocionService"""
    return PromocionService(firestore_service)
