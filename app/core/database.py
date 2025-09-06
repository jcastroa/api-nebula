"""Configuración de base de datos MySQL"""
from mysql.connector import pooling
import mysql.connector
from contextlib import contextmanager
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Pool de conexiones MySQL
mysql_pool = pooling.MySQLConnectionPool(
    pool_name="auth_pool",
    pool_size=settings.DB_POOL_SIZE,
    pool_reset_session=True,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME,
    charset='utf8mb4',
    autocommit=True
)

@contextmanager
def get_db_connection():
    """Context manager para obtener conexión"""
    conn = None
    try:
        conn = mysql_pool.get_connection()
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

