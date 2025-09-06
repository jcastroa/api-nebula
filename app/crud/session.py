# ==========================================
# app/crud/session.py - CRUD de sesiones
# ==========================================

"""CRUD operations para la tabla user_sessions"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.crud.base import BaseCRUD
from app.core.database import get_db_connection
import logging
import json

logger = logging.getLogger(__name__)

class SessionCRUD(BaseCRUD):
    """CRUD específico para sesiones de usuario"""
    
    def __init__(self):
        super().__init__(None)
    
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Obtener sesión por session_id"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT s.*, u.username, u.email
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.session_id = %s
                """, (session_id,))
                
                result = cursor.fetchone()
                if result and result['device_info']:
                    # Parsear JSON de device_info
                    try:
                        result['device_info'] = json.loads(result['device_info'])
                    except (json.JSONDecodeError, TypeError):
                        result['device_info'] = {}
                
                return result
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    async def get_by_user(
        self, 
        user_id: int, 
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """Obtener sesiones de un usuario por status"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT s.*, u.username, u.email
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.user_id = %s AND s.status = %s
                    ORDER BY s.last_activity DESC
                """, (user_id, status))
                
                results = cursor.fetchall()
                
                # Parsear device_info JSON
                for result in results:
                    if result['device_info']:
                        try:
                            result['device_info'] = json.loads(result['device_info'])
                        except (json.JSONDecodeError, TypeError):
                            result['device_info'] = {}
                
                return results
        except Exception as e:
            logger.error(f"Error getting sessions for user {user_id}: {e}")
            return []
    
    async def get_multi(
        self, 
        skip: int = 0, 
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Obtener múltiples sesiones con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                query = """
                    SELECT s.*, u.username, u.email
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE 1=1
                """
                params = []
                
                # Aplicar filtros
                if filters:
                    if filters.get('status'):
                        query += " AND s.status = %s"
                        params.append(filters['status'])
                    
                    if filters.get('user_id'):
                        query += " AND s.user_id = %s"
                        params.append(filters['user_id'])
                    
                    if filters.get('ip_address'):
                        query += " AND s.ip_address = %s"
                        params.append(filters['ip_address'])
                
                # Ordenar y paginar
                query += " ORDER BY s.created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, skip])
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                # Parsear device_info JSON
                for result in results:
                    if result['device_info']:
                        try:
                            result['device_info'] = json.loads(result['device_info'])
                        except (json.JSONDecodeError, TypeError):
                            result['device_info'] = {}
                
                return results
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []
    
    async def create(self, obj_in: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear nueva sesión"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO user_sessions 
                    (user_id, session_id, access_token_jti, refresh_token_jti,
                     device_info, ip_address, user_agent, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    obj_in['user_id'],
                    obj_in['session_id'],
                    obj_in['access_token_jti'],
                    obj_in['refresh_token_jti'],
                    json.dumps(obj_in.get('device_info', {})),
                    obj_in.get('ip_address'),
                    obj_in.get('user_agent'),
                    obj_in['expires_at']
                ))
                
                conn.commit()
                return await self.get(obj_in['session_id'])
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return None
    
    async def update(
        self, 
        session_id: str, 
        obj_in: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Actualizar sesión existente"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Campos actualizables
                fields = []
                params = []
                
                updateable_fields = [
                    'access_token_jti', 'refresh_token_jti', 
                    'last_activity', 'expires_at'
                ]
                
                for field in updateable_fields:
                    if field in obj_in:
                        fields.append(f"{field} = %s")
                        params.append(obj_in[field])
                
                if not fields:
                    return await self.get(session_id)
                
                query = f"UPDATE user_sessions SET {', '.join(fields)} WHERE session_id = %s"
                params.append(session_id)
                
                cursor.execute(query, params)
                conn.commit()
                
                return await self.get(session_id)
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            return None
    
    async def delete(self, session_id: str) -> bool:
        """Eliminar sesión (hard delete)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_sessions WHERE session_id = %s
                """, (session_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Contar sesiones con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT COUNT(*) FROM user_sessions WHERE 1=1"
                params = []
                
                if filters:
                    if filters.get('status'):
                        query += " AND status = %s"
                        params.append(filters['status'])
                    
                    if filters.get('user_id'):
                        query += " AND user_id = %s"
                        params.append(filters['user_id'])
                
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error counting sessions: {e}")
            return 0
    
    async def revoke_session(self, session_id: str, reason: str) -> bool:
        """Revocar sesión específica"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_sessions 
                    SET status = 'revoked', 
                        revoked_at = CURRENT_TIMESTAMP, 
                        revoked_reason = %s
                    WHERE session_id = %s AND status = 'active'
                """, (reason, session_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error revoking session {session_id}: {e}")
            return False
    
    async def revoke_user_sessions(
        self, 
        user_id: int, 
        reason: str, 
        exclude_session: Optional[str] = None
    ) -> int:
        """Revocar todas las sesiones de un usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                    UPDATE user_sessions 
                    SET status = 'revoked', 
                        revoked_at = CURRENT_TIMESTAMP, 
                        revoked_reason = %s
                    WHERE user_id = %s AND status = 'active'
                """
                params = [reason, user_id]
                
                if exclude_session:
                    query += " AND session_id != %s"
                    params.append(exclude_session)
                
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error revoking sessions for user {user_id}: {e}")
            return 0
    
    async def cleanup_expired_sessions(self, hours: int = 6) -> int:
        """Limpiar sesiones expiradas automáticamente"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                cursor.execute("""
                    UPDATE user_sessions 
                    SET status = 'expired', 
                        revoked_at = CURRENT_TIMESTAMP, 
                        revoked_reason = 'cleanup_job'
                    WHERE last_activity < %s AND status = 'active'
                """, (cutoff_time,))
                
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")
            return 0
    
    async def get_session_stats(self) -> Dict[str, int]:
        """Obtener estadísticas de sesiones"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Sesiones activas
                cursor.execute("SELECT COUNT(*) FROM user_sessions WHERE status = 'active'")
                stats['active_sessions'] = cursor.fetchone()[0]
                
                # Sesiones hoy
                cursor.execute("""
                    SELECT COUNT(*) FROM user_sessions 
                    WHERE DATE(created_at) = CURDATE()
                """)
                stats['sessions_today'] = cursor.fetchone()[0]
                
                # Usuarios únicos hoy
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) FROM user_sessions 
                    WHERE DATE(created_at) = CURDATE()
                """)
                stats['unique_users_today'] = cursor.fetchone()[0]
                
                # Total de sesiones
                cursor.execute("SELECT COUNT(*) FROM user_sessions")
                stats['total_sessions'] = cursor.fetchone()[0]
                
                # Sesiones por status
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM user_sessions 
                    GROUP BY status
                """)
                
                status_results = cursor.fetchall()
                for status, count in status_results:
                    stats[f'sessions_{status}'] = count
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {}
    
    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtener sesiones más recientes"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT s.session_id, s.user_id, u.username, s.ip_address,
                           s.created_at, s.last_activity, s.status
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    ORDER BY s.created_at DESC
                    LIMIT %s
                """, (limit,))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting recent sessions: {e}")
            return []
    
    async def get_user_session_history(
        self, 
        user_id: int, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Obtener historial de sesiones de un usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT session_id, ip_address, user_agent, device_info,
                           created_at, last_activity, expires_at, status,
                           revoked_at, revoked_reason
                    FROM user_sessions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                
                results = cursor.fetchall()
                
                # Parsear device_info JSON
                for result in results:
                    if result['device_info']:
                        try:
                            result['device_info'] = json.loads(result['device_info'])
                        except (json.JSONDecodeError, TypeError):
                            result['device_info'] = {}
                
                return results
        except Exception as e:
            logger.error(f"Error getting session history for user {user_id}: {e}")
            return []
    
    async def clean_old_sessions(self, days: int = 30) -> int:
        """Limpiar sesiones muy antiguas (hard delete)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                cursor.execute("""
                    DELETE FROM user_sessions 
                    WHERE created_at < %s 
                    AND status IN ('expired', 'revoked')
                """, (cutoff_date,))
                
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error cleaning old sessions: {e}")
            return 0
    
    async def get_active_sessions_by_ip(self, ip_address: str) -> List[Dict[str, Any]]:
        """Obtener sesiones activas por IP (para detección de abuso)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT s.session_id, s.user_id, u.username, s.created_at,
                           s.last_activity, s.user_agent
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.ip_address = %s AND s.status = 'active'
                    ORDER BY s.created_at DESC
                """, (ip_address,))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting sessions by IP {ip_address}: {e}")
            return []
    
    async def update_last_activity(self, session_id: str) -> bool:
        """Actualizar última actividad de una sesión"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_sessions 
                    SET last_activity = CURRENT_TIMESTAMP
                    WHERE session_id = %s AND status = 'active'
                """, (session_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating last activity for session {session_id}: {e}")
            return False