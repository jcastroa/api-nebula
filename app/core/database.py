"""Configuración de base de datos MySQL sin pool"""
import mysql.connector
from contextlib import contextmanager
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def _create_connection():
    """Crea una nueva conexión a MySQL"""
    return mysql.connector.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset='utf8mb4',
        autocommit=False,  # Mejor manejar transacciones manualmente
        buffered=True  # Importante: evita el error "Unread result found"
    )

@contextmanager
def get_db_connection():
    """Context manager para obtener conexión"""
    conn = None
    try:
        conn = _create_connection()
        yield conn
        conn.commit()  # Commit automático si todo va bien
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

@contextmanager
def get_db_cursor(dictionary=True):
    """Context manager que maneja conexión Y cursor"""
    conn = None
    cursor = None
    try:
        conn = _create_connection()
        cursor = conn.cursor(dictionary=dictionary, buffered=True)
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()