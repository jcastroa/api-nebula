"""
Service layer for medio_pago (payment methods) management.
Handles transaction logic between MariaDB and Firestore.
"""

from typing import Dict, Any, Optional, List
from firebase_admin import firestore
import logging
import mysql.connector
from app.services.firestore_service import FirestoreService


logger = logging.getLogger(__name__)


class MedioPagoService:
    """Service for managing payment methods with dual persistence (MariaDB + Firestore)"""

    def __init__(self, firestore_service: FirestoreService):
        self.firestore_service = firestore_service
        self.db = firestore_service.db

    def _normalize_payment_name_for_firestore(self, descripcion: str) -> str:
        """
        Convert payment method description to lowercase with underscores for Firestore key.

        Args:
            descripcion: Payment method description (e.g., "Tarjeta de Crédito")

        Returns:
            Normalized name (e.g., "tarjeta_de_credito")
        """
        # Replace spaces with underscores and convert to lowercase
        normalized = descripcion.strip().lower().replace(' ', '_')
        # Remove special characters (keep only alphanumeric and underscores)
        normalized = ''.join(c if c.isalnum() or c == '_' else '_' for c in normalized)
        # Replace multiple consecutive underscores with single underscore
        while '__' in normalized:
            normalized = normalized.replace('__', '_')
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        return normalized

    async def sync_all_payment_methods_to_firestore(
        self,
        negocio_id: int,
        medios_pago: List[Dict[str, Any]]
    ) -> None:
        """
        Sync all payment methods for a business to Firestore.
        Updates the 'medios_pago' array and 'datos_pago' map in the negocios collection.

        Structure in Firestore:
        {
            "medios_pago": ["tarjeta_de_credito", "transferencia_bancaria", ...],
            "datos_pago": {
                "tarjeta_de_credito": {
                    "nombre": "Juan Pérez",
                    "numero": "****1234"
                },
                "transferencia_bancaria": {
                    "nombre": "Cuenta Empresa",
                    "numero": "1234567890"
                }
            }
        }

        Args:
            negocio_id: Business ID
            medios_pago: List of payment method dictionaries

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            # Build medios_pago array and datos_pago map
            medios_pago_array = []
            datos_pago_map = {}

            for medio_pago in medios_pago:
                descripcion = medio_pago.get('descripcion', '')
                nombre_titular = medio_pago.get('nombre_titular', '')
                numero_cuenta = medio_pago.get('numero_cuenta', '')

                # Normalize description for Firestore key
                key = self._normalize_payment_name_for_firestore(descripcion)
                medios_pago_array.append(key)

                # Build datos_pago entry
                datos_pago_map[key] = {
                    'nombre': nombre_titular or '',
                    'numero': numero_cuenta or ''
                }

            logger.info(
                f"Syncing {len(medios_pago_array)} payment methods to Firestore "
                f"for negocio_id {negocio_id}"
            )

            # Update Firestore document in 'negocios' collection
            doc_ref = self.db.collection('negocios').document(str(negocio_id))

            # Use update() to set medios_pago and datos_pago
            # This ensures deleted payment methods are removed from Firestore
            try:
                doc_ref.update({
                    'medios_pago': medios_pago_array,
                    'datos_pago': datos_pago_map,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                # If document doesn't exist, create it with set()
                if 'NOT_FOUND' in str(e) or 'not found' in str(e).lower():
                    logger.info(f"Document not found for negocio_id {negocio_id}, creating new document")
                    doc_ref.set({
                        'medios_pago': medios_pago_array,
                        'datos_pago': datos_pago_map,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                else:
                    raise

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for negocio_id {negocio_id}: {str(e)}")
            raise Exception(f"Error al sincronizar con Firestore: {str(e)}")

    async def create_medio_pago_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int,
        descripcion: str,
        detalle: str,
        nombre_titular: Optional[str],
        numero_cuenta: Optional[str],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create payment method within an existing MariaDB transaction.
        This method is called by the endpoint after starting a transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            negocio_id: Business ID
            descripcion: Payment method description
            detalle: Payment method details
            nombre_titular: Account holder name
            numero_cuenta: Account number
            user_id: User ID

        Returns:
            Created payment method dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            cursor.execute(
                """
                INSERT INTO medios_pago
                    (negocio_id, descripcion, detalle, nombre_titular, numero_cuenta, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (negocio_id, descripcion, detalle, nombre_titular, numero_cuenta, user_id)
            )

            medio_pago_id = cursor.lastrowid

            # Get the created record
            cursor.execute(
                """
                SELECT
                    id,
                    negocio_id,
                    descripcion,
                    detalle,
                    nombre_titular,
                    numero_cuenta,
                    activo,
                    eliminado,
                    created_at,
                    updated_at,
                    created_by,
                    updated_by
                FROM medios_pago
                WHERE id = %s
                """,
                (medio_pago_id,)
            )
            result = cursor.fetchone()

            if not result:
                raise Exception("Failed to retrieve created payment method")

            # Convert tuple to dictionary (if cursor is not dictionary=True)
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            logger.info(f"Payment method created in MariaDB: id={medio_pago_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error creating payment method in MariaDB: {str(e)}")
            raise

    async def update_medio_pago_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        medio_pago_id: int,
        negocio_id: int,
        descripcion: Optional[str] = None,
        detalle: Optional[str] = None,
        nombre_titular: Optional[str] = None,
        numero_cuenta: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update payment method within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            medio_pago_id: Payment method ID
            negocio_id: Business ID
            descripcion: Payment method description (optional)
            detalle: Payment method details (optional)
            nombre_titular: Account holder name (optional)
            numero_cuenta: Account number (optional)
            user_id: User ID

        Returns:
            Updated payment method dictionary or None if not found

        Raises:
            Exception: If database operation fails
        """
        try:
            # Build dynamic update query
            update_fields = []
            params = []

            if descripcion is not None:
                update_fields.append("descripcion = %s")
                params.append(descripcion)

            if detalle is not None:
                update_fields.append("detalle = %s")
                params.append(detalle)

            if nombre_titular is not None:
                update_fields.append("nombre_titular = %s")
                params.append(nombre_titular)

            if numero_cuenta is not None:
                update_fields.append("numero_cuenta = %s")
                params.append(numero_cuenta)

            # Always update updated_by
            update_fields.append("updated_by = %s")
            params.append(user_id)

            if not update_fields:
                # No fields to update, just return current record
                cursor.execute(
                    """
                    SELECT
                        id, negocio_id, descripcion, detalle, nombre_titular,
                        numero_cuenta, activo, eliminado, created_at, updated_at,
                        created_by, updated_by
                    FROM medios_pago
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE AND activo = TRUE
                    """,
                    (medio_pago_id, negocio_id)
                )
                result = cursor.fetchone()
            else:
                # Add WHERE clause parameters
                params.extend([medio_pago_id, negocio_id])

                query = f"""
                    UPDATE medios_pago
                    SET {', '.join(update_fields)}
                    WHERE id = %s AND negocio_id = %s AND eliminado = FALSE AND activo = TRUE
                """

                cursor.execute(query, params)
                rows_affected = cursor.rowcount

                if rows_affected == 0:
                    return None

                # Get the updated record
                cursor.execute(
                    """
                    SELECT
                        id, negocio_id, descripcion, detalle, nombre_titular,
                        numero_cuenta, activo, eliminado, created_at, updated_at,
                        created_by, updated_by
                    FROM medios_pago
                    WHERE id = %s
                    """,
                    (medio_pago_id,)
                )
                result = cursor.fetchone()

            if not result:
                return None

            # Convert tuple to dictionary
            if isinstance(result, tuple):
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, result))

            logger.info(f"Payment method updated in MariaDB: id={medio_pago_id}, negocio_id={negocio_id}")
            return result

        except Exception as e:
            logger.error(f"Error updating payment method in MariaDB: {str(e)}")
            raise

    async def delete_medio_pago_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        medio_pago_id: int,
        negocio_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Soft delete payment method within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            medio_pago_id: Payment method ID
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
                UPDATE medios_pago
                SET eliminado = TRUE, activo = FALSE, updated_by = %s
                WHERE id = %s AND negocio_id = %s AND eliminado = FALSE
                """,
                (user_id, medio_pago_id, negocio_id)
            )
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                logger.info(
                    f"Payment method soft deleted in MariaDB: "
                    f"id={medio_pago_id}, negocio_id={negocio_id}"
                )
                return True
            else:
                logger.warning(
                    f"Payment method not found for deletion: "
                    f"id={medio_pago_id}, negocio_id={negocio_id}"
                )
                return False

        except Exception as e:
            logger.error(f"Error deleting payment method in MariaDB: {str(e)}")
            raise

    async def get_all_active_payment_methods(
        self,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all active payment methods for Firestore sync.

        Args:
            cursor: Active database cursor
            negocio_id: Business ID

        Returns:
            List of active payment methods
        """
        cursor.execute(
            """
            SELECT descripcion, nombre_titular, numero_cuenta
            FROM medios_pago
            WHERE negocio_id = %s AND eliminado = FALSE AND activo = TRUE
            ORDER BY descripcion
            """,
            (negocio_id,)
        )
        results = cursor.fetchall()

        # Convert to list of dictionaries
        payment_methods = []
        for row in results:
            if isinstance(row, tuple):
                payment_methods.append({
                    'descripcion': row[0],
                    'nombre_titular': row[1],
                    'numero_cuenta': row[2]
                })
            else:
                payment_methods.append(row)

        return payment_methods


# Dependency injection helper
def get_medio_pago_service(
    firestore_service: FirestoreService
) -> MedioPagoService:
    """FastAPI dependency for MedioPagoService"""
    return MedioPagoService(firestore_service)
