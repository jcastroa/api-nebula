"""
Service layer for chatbot configuration management.
Handles transaction logic between MariaDB and Firestore.
"""

from typing import Dict, Any, Optional
from firebase_admin import firestore
from app.core.logging import logger
from app.core.database import get_db_connection
from app.services.firestore_service import FirestoreService
import json
import mysql.connector


class ChatbotConfiguracionService:
    """Service for managing chatbot configuration with dual persistence"""

    def __init__(self, firestore_service: FirestoreService):
        self.firestore_service = firestore_service
        self.db = firestore_service.db

    async def save_configuracion_with_transaction(
        self,
        negocio_id: int,
        configuracion: Dict[str, Any],
        prompt_completo: str
    ) -> Dict[str, Any]:
        """
        Save chatbot configuration to both MariaDB and Firestore using transactions.
        Implements rollback if either operation fails.

        Args:
            negocio_id: Business/consultorio ID
            configuracion: Structured configuration dictionary
            prompt_completo: Complete prompt text

        Returns:
            Dictionary with id, negocio_id, and updated_at

        Raises:
            Exception: If either database operation fails
        """
        conn = None
        mariadb_success = False

        try:
            # ==========================================
            # STEP 1: MariaDB Operation (within transaction)
            # ==========================================
            logger.info(f"Starting transaction for negocio_id {negocio_id}")

            # Get connection manually (don't use context manager yet)
            conn = mysql.connector.connect(
                host=self._get_db_config('DB_HOST'),
                port=int(self._get_db_config('DB_PORT')),
                user=self._get_db_config('DB_USER'),
                password=self._get_db_config('DB_PASSWORD'),
                database=self._get_db_config('DB_NAME'),
                charset='utf8mb4',
                autocommit=False,  # Important: disable autocommit for transactions
                buffered=True
            )

            cursor = conn.cursor(dictionary=True)

            # Convert configuration to JSON string
            configuracion_json = json.dumps(configuracion, ensure_ascii=False)

            # UPSERT in MariaDB
            cursor.execute(
                """
                INSERT INTO chatbot_configuracion
                    (negocio_id, configuracion, prompt_completo, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    configuracion = VALUES(configuracion),
                    prompt_completo = VALUES(prompt_completo),
                    updated_at = NOW()
                """,
                (negocio_id, configuracion_json, prompt_completo)
            )

            # Get the inserted/updated record
            cursor.execute(
                """
                SELECT id, negocio_id, updated_at
                FROM chatbot_configuracion
                WHERE negocio_id = %s
                """,
                (negocio_id,)
            )
            result = cursor.fetchone()
            cursor.close()

            if not result:
                raise Exception("Failed to retrieve saved configuration from MariaDB")

            logger.info(f"MariaDB operation successful for negocio_id {negocio_id}")
            mariadb_success = True

            # ==========================================
            # STEP 2: Firestore Operation
            # ==========================================
            try:
                logger.info(f"Saving to Firestore collection 'conocimiento_gpt'")

                doc_ref = self.db.collection('conocimiento_gpt').document(str(negocio_id))

                doc_ref.set({
                    'negocio_id': negocio_id,
                    'prompt_completo': prompt_completo,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })

                logger.info(f"Firestore operation successful for negocio_id {negocio_id}")

            except Exception as firestore_error:
                # Firestore failed - ROLLBACK MariaDB
                logger.error(f"Firestore operation failed: {str(firestore_error)}")
                conn.rollback()
                logger.warning(f"MariaDB transaction rolled back for negocio_id {negocio_id}")

                raise Exception(
                    f"Error al guardar en Firestore: {str(firestore_error)}. "
                    "La transacción ha sido revertida."
                )

            # ==========================================
            # STEP 3: Commit if both operations succeeded
            # ==========================================
            conn.commit()
            logger.info(f"Transaction committed successfully for negocio_id {negocio_id}")

            return {
                "id": result['id'],
                "negocio_id": result['negocio_id'],
                "updated_at": result['updated_at'].isoformat() if result['updated_at'] else None
            }

        except mysql.connector.Error as db_error:
            # MariaDB operation failed
            logger.error(f"MariaDB operation failed: {str(db_error)}")
            if conn and mariadb_success:
                conn.rollback()
                logger.warning(f"MariaDB transaction rolled back for negocio_id {negocio_id}")

            raise Exception(f"Error al guardar en MariaDB: {str(db_error)}")

        except Exception as e:
            # Any other error
            logger.error(f"Unexpected error during transaction: {str(e)}")
            if conn and mariadb_success:
                conn.rollback()
                logger.warning(f"MariaDB transaction rolled back for negocio_id {negocio_id}")

            raise

        finally:
            # Always close the connection
            if conn and conn.is_connected():
                conn.close()
                logger.debug(f"Connection closed for negocio_id {negocio_id}")

    async def get_configuracion_from_mariadb(self, negocio_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chatbot configuration from MariaDB only.

        Args:
            negocio_id: Business/consultorio ID

        Returns:
            Configuration dictionary or None if not found
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT
                        id,
                        negocio_id,
                        configuracion,
                        prompt_completo,
                        created_at,
                        updated_at
                    FROM chatbot_configuracion
                    WHERE negocio_id = %s
                    """,
                    (negocio_id,)
                )
                result = cursor.fetchone()
                cursor.close()

                if result and result.get('configuracion'):
                    # Parse JSON configuration
                    if isinstance(result['configuracion'], str):
                        result['configuracion'] = json.loads(result['configuracion'])

                return result

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON configuration for negocio_id {negocio_id}: {str(e)}")
            raise ValueError(f"Configuración JSON inválida: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting chatbot configuration for negocio_id {negocio_id}: {str(e)}")
            raise

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
def get_chatbot_service(
    firestore_service: FirestoreService
) -> ChatbotConfiguracionService:
    """FastAPI dependency for ChatbotConfiguracionService"""
    return ChatbotConfiguracionService(firestore_service)
