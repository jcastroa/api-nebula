"""
CRUD operations for chatbot_configuracion table.
Handles database operations for chatbot configuration management.
"""

import json
from typing import Optional, Dict, Any
from app.core.database import get_db_connection
from app.core.logging import logger


class ChatbotConfiguracionCRUD:
    """CRUD operations for chatbot configuration"""

    async def get_by_negocio_id(self, negocio_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chatbot configuration by negocio_id from MariaDB.

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
            raise ValueError(f"Invalid JSON configuration: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting chatbot configuration for negocio_id {negocio_id}: {str(e)}")
            raise

    async def upsert_with_transaction(
        self,
        negocio_id: int,
        configuracion: Dict[str, Any],
        prompt_completo: str
    ) -> Dict[str, Any]:
        """
        Insert or update chatbot configuration using transaction.
        This method is designed to work with Firestore transaction in the service layer.

        Args:
            negocio_id: Business/consultorio ID
            configuracion: Structured configuration dictionary
            prompt_completo: Complete prompt text

        Returns:
            Dictionary with id, negocio_id, and updated_at

        Raises:
            Exception: If database operation fails (caller should rollback)
        """
        conn = None
        try:
            conn = get_db_connection().__enter__()
            cursor = conn.cursor(dictionary=True)

            # Start transaction (autocommit is False in context manager)
            # Convert configuration to JSON string
            configuracion_json = json.dumps(configuracion, ensure_ascii=False)

            # UPSERT: Insert or update if negocio_id already exists
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
                raise Exception("Failed to retrieve saved configuration")

            # Note: Commit will be handled by context manager or explicitly by caller
            return result

        except Exception as e:
            logger.error(f"Error upserting chatbot configuration for negocio_id {negocio_id}: {str(e)}")
            if conn:
                conn.rollback()
            raise
        finally:
            # Don't close connection here - let service layer handle it
            # to maintain transaction context
            pass

    def commit_transaction(self, conn) -> None:
        """
        Commit the transaction.

        Args:
            conn: Database connection
        """
        try:
            if conn and conn.is_connected():
                conn.commit()
                logger.info("Transaction committed successfully")
        except Exception as e:
            logger.error(f"Error committing transaction: {str(e)}")
            raise

    def rollback_transaction(self, conn) -> None:
        """
        Rollback the transaction.

        Args:
            conn: Database connection
        """
        try:
            if conn and conn.is_connected():
                conn.rollback()
                logger.warning("Transaction rolled back")
        except Exception as e:
            logger.error(f"Error rolling back transaction: {str(e)}")
            raise

    def close_connection(self, conn) -> None:
        """
        Close the database connection.

        Args:
            conn: Database connection
        """
        try:
            if conn and conn.is_connected():
                conn.close()
                logger.debug("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")

    async def delete_by_negocio_id(self, negocio_id: int) -> bool:
        """
        Delete chatbot configuration by negocio_id.

        Args:
            negocio_id: Business/consultorio ID

        Returns:
            True if deleted, False if not found
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM chatbot_configuracion WHERE negocio_id = %s",
                    (negocio_id,)
                )
                rows_affected = cursor.rowcount
                cursor.close()

                return rows_affected > 0

        except Exception as e:
            logger.error(f"Error deleting chatbot configuration for negocio_id {negocio_id}: {str(e)}")
            raise


# Dependency injection helper
def get_chatbot_configuracion_crud() -> ChatbotConfiguracionCRUD:
    """FastAPI dependency for ChatbotConfiguracionCRUD"""
    return ChatbotConfiguracionCRUD()
