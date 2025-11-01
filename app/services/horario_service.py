"""
Service layer for horarios (business hours) management.
Handles transaction logic between MariaDB and Firestore.
"""

from typing import Dict, Any, Optional, List
from firebase_admin import firestore
import logging
import mysql.connector
from datetime import date, timedelta
from app.services.firestore_service import FirestoreService


logger = logging.getLogger(__name__)


# Mapping of Spanish day names to day numbers (1=Monday, 7=Sunday)
DIA_SEMANA_MAP = {
    'lunes': 1,
    'martes': 2,
    'miercoles': 3,
    'jueves': 4,
    'viernes': 5,
    'sabado': 6,
    'domingo': 7
}

# Reverse mapping
DIA_NUMERO_MAP = {v: k for k, v in DIA_SEMANA_MAP.items()}


class HorarioService:
    """Service for managing business hours with dual persistence (MariaDB + Firestore)"""

    def __init__(self, firestore_service: FirestoreService):
        self.firestore_service = firestore_service
        self.db = firestore_service.db

    async def save_horarios_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int,
        dias_laborables: Dict[str, bool],
        horarios: Dict[str, List[Dict[str, str]]],
        intervalo_citas: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Save business hours within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            negocio_id: Business ID
            dias_laborables: Working days configuration
            horarios: Business hours per day
            intervalo_citas: Appointment interval in minutes
            user_id: User ID

        Returns:
            True if successful

        Raises:
            Exception: If database operation fails
        """
        try:
            # Step 1: Delete existing horarios for this negocio (soft delete)
            cursor.execute(
                """
                UPDATE horarios_atencion
                SET eliminado = 1, eliminado_por = %s, fecha_eliminacion = NOW()
                WHERE negocio_id = %s
                """,
                (user_id, negocio_id)
            )
            logger.info(f"Soft deleted existing horarios for negocio_id {negocio_id}")

            # Step 2: Insert new horarios
            for dia_nombre, rangos in horarios.items():
                dia_numero = DIA_SEMANA_MAP.get(dia_nombre.lower())
                if dia_numero is None:
                    logger.warning(f"Invalid day name: {dia_nombre}")
                    continue

                # Insert each time range for this day
                for rango in rangos:
                    cursor.execute(
                        """
                        INSERT INTO horarios_atencion
                            (negocio_id, dia_semana, hora_inicio, hora_fin, creado_por)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (negocio_id, dia_numero, rango['inicio'], rango['fin'], user_id)
                    )

            logger.info(f"Inserted new horarios for negocio_id {negocio_id}")

            # Step 3: Update intervalo_citas in consultorios table
            cursor.execute(
                """
                UPDATE consultorios
                SET intervalo_citas = %s, actualizado_por = %s, fecha_actualizacion = NOW()
                WHERE id = %s
                """,
                (intervalo_citas, user_id, negocio_id)
            )

            rows_affected = cursor.rowcount
            if rows_affected == 0:
                logger.warning(f"No consultorio found with id {negocio_id}")
                # Don't fail, just log warning

            logger.info(f"Updated intervalo_citas in consultorios for negocio_id {negocio_id}")

            return True

        except Exception as e:
            logger.error(f"Error saving horarios in MariaDB: {str(e)}")
            raise

    async def sync_horarios_to_firestore(
        self,
        negocio_id: int,
        horarios: Dict[str, List[Dict[str, str]]],
        intervalo_citas: int
    ) -> None:
        """
        Sync business hours to Firestore.
        Updates the 'horarios', 'intervalo_citas', and 'duracion_cita' fields in the negocios collection.
        Only saves days that have configured hours (non-empty arrays).

        Args:
            negocio_id: Business ID
            horarios: Business hours per day
            intervalo_citas: Appointment interval in minutes (also used for duracion_cita)

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            logger.info(f"Syncing horarios to Firestore for negocio_id {negocio_id}")

            # Update Firestore document in 'negocios' collection
            doc_ref = self.db.collection('negocios').document(str(negocio_id))

            # Prepare horarios for Firestore - only include days with configured hours
            firestore_horarios = {}
            for dia, rangos in horarios.items():
                # Only add days that have at least one time range
                if rangos and len(rangos) > 0:
                    firestore_horarios[dia] = rangos

            # Update or create document
            try:
                doc_ref.update({
                    'horarios': firestore_horarios,
                    'intervalo_citas': intervalo_citas,
                    'duracion_cita': intervalo_citas,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                # If document doesn't exist, create it
                if 'NOT_FOUND' in str(e) or 'not found' in str(e).lower():
                    logger.info(f"Document not found for negocio_id {negocio_id}, creating new document")
                    doc_ref.set({
                        'horarios': firestore_horarios,
                        'intervalo_citas': intervalo_citas,
                        'duracion_cita': intervalo_citas,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                else:
                    raise

            logger.info(f"Firestore sync successful for negocio_id {negocio_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for negocio_id {negocio_id}: {str(e)}")
            raise Exception(f"Error al sincronizar con Firestore: {str(e)}")

    async def get_horarios_from_mariadb(
        self,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int
    ) -> Dict[str, Any]:
        """
        Get business hours from MariaDB.

        Args:
            cursor: Active database cursor
            negocio_id: Business ID

        Returns:
            Dictionary with dias_laborables, horarios, and intervalo_citas
        """
        try:
            # Get active horarios
            cursor.execute(
                """
                SELECT dia_semana, hora_inicio, hora_fin
                FROM horarios_atencion
                WHERE negocio_id = %s AND eliminado = 0
                ORDER BY dia_semana, hora_inicio
                """,
                (negocio_id,)
            )
            results = cursor.fetchall()

            # Get intervalo_citas from consultorios table
            cursor.execute(
                """
                SELECT intervalo_citas
                FROM consultorios
                WHERE id = %s
                """,
                (negocio_id,)
            )
            consultorio_result = cursor.fetchone()

            # Default intervalo_citas if not found or NULL
            intervalo_citas = 30
            if consultorio_result:
                if isinstance(consultorio_result, tuple):
                    intervalo_citas = consultorio_result[0] if consultorio_result[0] is not None else 30
                else:
                    # Get value from dict, use 30 if None or not found
                    intervalo_citas = consultorio_result.get('intervalo_citas')
                    if intervalo_citas is None:
                        intervalo_citas = 30

            # Initialize all days
            dias_laborables = {
                'lunes': False,
                'martes': False,
                'miercoles': False,
                'jueves': False,
                'viernes': False,
                'sabado': False,
                'domingo': False
            }

            horarios = {
                'lunes': [],
                'martes': [],
                'miercoles': [],
                'jueves': [],
                'viernes': [],
                'sabado': [],
                'domingo': []
            }

            # Process results
            for row in results:
                if isinstance(row, tuple):
                    dia_numero, hora_inicio, hora_fin = row
                else:
                    dia_numero = row.get('dia_semana')
                    hora_inicio = row.get('hora_inicio')
                    hora_fin = row.get('hora_fin')

                dia_nombre = DIA_NUMERO_MAP.get(dia_numero)
                if dia_nombre is None:
                    logger.warning(f"Invalid day number: {dia_numero}")
                    continue

                # Mark day as working day
                dias_laborables[dia_nombre] = True

                # Convert time objects to string format HH:MM
                if hora_inicio is not None:
                    # Handle both time objects and timedelta objects
                    if hasattr(hora_inicio, 'strftime'):
                        hora_inicio_str = hora_inicio.strftime('%H:%M')
                    else:
                        # If it's a timedelta, convert to hours:minutes
                        total_seconds = int(hora_inicio.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        hora_inicio_str = f"{hours:02d}:{minutes:02d}"
                else:
                    hora_inicio_str = "00:00"

                if hora_fin is not None:
                    if hasattr(hora_fin, 'strftime'):
                        hora_fin_str = hora_fin.strftime('%H:%M')
                    else:
                        total_seconds = int(hora_fin.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        hora_fin_str = f"{hours:02d}:{minutes:02d}"
                else:
                    hora_fin_str = "00:00"

                # Add time range
                horarios[dia_nombre].append({
                    'inicio': hora_inicio_str,
                    'fin': hora_fin_str
                })

            return {
                'dias_laborables': dias_laborables,
                'horarios': horarios,
                'intervalo_citas': intervalo_citas
            }

        except Exception as e:
            logger.error(f"Error getting horarios from MariaDB: {str(e)}")
            raise

    # ===== Excepciones (Non-working days) =====

    async def create_excepcion_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int,
        tipo: str,
        fecha_inicio: date,
        fecha_fin: Optional[date],
        motivo: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create an exception (non-working day) within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            negocio_id: Business ID
            tipo: Exception type (feriado, vacaciones, otro)
            fecha_inicio: Start date
            fecha_fin: End date (optional, can be same as fecha_inicio)
            motivo: Reason for the exception
            user_id: User ID

        Returns:
            Created exception dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            # If fecha_fin is not provided, use fecha_inicio
            if fecha_fin is None:
                fecha_fin = fecha_inicio

            cursor.execute(
                """
                INSERT INTO dias_no_laborables
                    (negocio_id, tipo_excepcion, fecha_inicio, fecha_fin, motivo, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (negocio_id, tipo, fecha_inicio, fecha_fin, motivo, user_id)
            )

            excepcion_id = cursor.lastrowid

            # Get the created record
            cursor.execute(
                """
                SELECT id, tipo_excepcion, fecha_inicio, fecha_fin, motivo
                FROM dias_no_laborables
                WHERE id = %s
                """,
                (excepcion_id,)
            )
            result = cursor.fetchone()

            if not result:
                raise Exception("Failed to retrieve created exception")

            # Convert to dictionary
            if isinstance(result, tuple):
                return {
                    'id': result[0],
                    'tipo': result[1],
                    'fecha_inicio': result[2],
                    'fecha_fin': result[3],
                    'motivo': result[4]
                }
            else:
                return {
                    'id': result['id'],
                    'tipo': result['tipo_excepcion'],
                    'fecha_inicio': result['fecha_inicio'],
                    'fecha_fin': result['fecha_fin'],
                    'motivo': result['motivo']
                }

        except Exception as e:
            logger.error(f"Error creating exception in MariaDB: {str(e)}")
            raise

    async def get_excepciones_from_mariadb(
        self,
        cursor: mysql.connector.cursor.MySQLCursor,
        negocio_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all active exceptions for a business from MariaDB.

        Args:
            cursor: Active database cursor
            negocio_id: Business ID

        Returns:
            List of exception dictionaries
        """
        try:
            cursor.execute(
                """
                SELECT id, tipo_excepcion, fecha_inicio, fecha_fin, motivo
                FROM dias_no_laborables
                WHERE negocio_id = %s AND eliminado = 0
                ORDER BY fecha_inicio DESC
                """,
                (negocio_id,)
            )
            results = cursor.fetchall()

            excepciones = []
            for row in results:
                if isinstance(row, tuple):
                    excepciones.append({
                        'id': row[0],
                        'tipo': row[1],
                        'fecha_inicio': row[2],
                        'fecha_fin': row[3],
                        'motivo': row[4]
                    })
                else:
                    excepciones.append({
                        'id': row['id'],
                        'tipo': row['tipo_excepcion'],
                        'fecha_inicio': row['fecha_inicio'],
                        'fecha_fin': row['fecha_fin'],
                        'motivo': row['motivo']
                    })

            return excepciones

        except Exception as e:
            logger.error(f"Error getting excepciones from MariaDB: {str(e)}")
            raise

    async def delete_excepcion_with_transaction(
        self,
        conn: mysql.connector.MySQLConnection,
        cursor: mysql.connector.cursor.MySQLCursor,
        excepcion_id: int,
        negocio_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Soft delete an exception within an existing MariaDB transaction.

        Args:
            conn: Active database connection
            cursor: Active database cursor
            excepcion_id: Exception ID
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
                UPDATE dias_no_laborables
                SET eliminado = 1, eliminado_por = %s, fecha_eliminacion = NOW()
                WHERE id = %s AND negocio_id = %s AND eliminado = 0
                """,
                (user_id, excepcion_id, negocio_id)
            )
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                logger.info(f"Exception soft deleted in MariaDB: id={excepcion_id}, negocio_id={negocio_id}")
                return True
            else:
                logger.warning(f"Exception not found for deletion: id={excepcion_id}, negocio_id={negocio_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting exception in MariaDB: {str(e)}")
            raise

    async def sync_excepcion_to_firestore(
        self,
        excepcion_id: int,
        negocio_id: int,
        tipo: str,
        fecha_inicio: date,
        fecha_fin: Optional[date],
        motivo: str
    ) -> None:
        """
        Sync a single exception to Firestore.
        Creates/updates a document in 'dias_no_laborales' collection using MySQL ID.

        Structure in Firestore:
        dias_no_laborales/{excepcion_id}/
          {
            "fecha": "2024-12-25",
            "negocio_id": 123,
            "nombre": "feriado - Navidad"
          }

        Args:
            excepcion_id: Exception ID from MySQL
            negocio_id: Business ID
            tipo: Exception type
            fecha_inicio: Start date
            fecha_fin: End date (optional)
            motivo: Reason for exception

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            logger.info(f"Syncing excepcion {excepcion_id} to Firestore for negocio_id {negocio_id}")

            # Create nombre: "tipo - motivo"
            nombre = f"{tipo} - {motivo}"

            # Convert to date if it's a datetime
            if hasattr(fecha_inicio, 'date'):
                fecha_inicio = fecha_inicio.date()

            # If no fecha_fin, use fecha_inicio
            if not fecha_fin:
                fecha_fin = fecha_inicio
            elif hasattr(fecha_fin, 'date'):
                fecha_fin = fecha_fin.date()

            # Format date as ISO string (YYYY-MM-DD)
            fecha_str = fecha_inicio.strftime('%Y-%m-%d')

            # Prepare data for Firestore
            firestore_data = {
                'fecha': fecha_str,
                'negocio_id': negocio_id,
                'nombre': nombre,
                'updated_at': firestore.SERVER_TIMESTAMP
            }

            # Update Firestore document in 'dias_no_laborales' collection
            # Use the MySQL ID as the document ID
            doc_ref = self.db.collection('dias_no_laborales').document(str(excepcion_id))
            doc_ref.set(firestore_data)

            logger.info(f"Firestore sync successful for excepcion_id {excepcion_id}")

        except Exception as e:
            logger.error(f"Firestore sync failed for excepcion_id {excepcion_id}: {str(e)}")
            raise Exception(f"Error al sincronizar excepción con Firestore: {str(e)}")

    async def delete_excepcion_from_firestore(
        self,
        excepcion_id: int
    ) -> None:
        """
        Delete an exception from Firestore.

        Args:
            excepcion_id: Exception ID from MySQL

        Raises:
            Exception: If Firestore operation fails
        """
        try:
            logger.info(f"Deleting excepcion {excepcion_id} from Firestore")

            # Delete document from 'dias_no_laborales' collection
            doc_ref = self.db.collection('dias_no_laborales').document(str(excepcion_id))
            doc_ref.delete()

            logger.info(f"Firestore delete successful for excepcion_id {excepcion_id}")

        except Exception as e:
            logger.error(f"Firestore delete failed for excepcion_id {excepcion_id}: {str(e)}")
            raise Exception(f"Error al eliminar excepción de Firestore: {str(e)}")


# Dependency injection helper
def get_horario_service(
    firestore_service: FirestoreService
) -> HorarioService:
    """FastAPI dependency for HorarioService"""
    return HorarioService(firestore_service)
