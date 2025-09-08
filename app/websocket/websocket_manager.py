# ==========================================
# app/websocket/websocket_manager.py - Manager de WebSocket
# ==========================================

"""Manager para conexiones WebSocket por negocio"""
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect
import logging
import json
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Manager para manejar conexiones WebSocket segmentadas por negocio
    """
    
    def __init__(self):
        # Estructura: {codigo_negocio: {user_id: websocket}}
        self.active_connections: Dict[str, Dict[int, WebSocket]] = {}
        
        # Metadata de conexiones
        self.connection_metadata: Dict[str, Dict[int, Dict]] = {}
        
        # Lock para operaciones thread-safe
        self._lock = asyncio.Lock()
    
    async def connect(
        self, 
        websocket: WebSocket, 
        user_id: int, 
        codigo_negocio: str,
        user_info: Dict = None
    ):
        """
        Conectar usuario a WebSocket para un negocio específico
        
        Args:
            websocket: Conexión WebSocket
            user_id: ID del usuario
            codigo_negocio: Código del negocio
            user_info: Información adicional del usuario
        """
        async with self._lock:
            await websocket.accept()
            
            # Inicializar negocio si no existe
            if codigo_negocio not in self.active_connections:
                self.active_connections[codigo_negocio] = {}
                self.connection_metadata[codigo_negocio] = {}
            
            # Guardar conexión
            self.active_connections[codigo_negocio][user_id] = websocket
            
            # Guardar metadata
            self.connection_metadata[codigo_negocio][user_id] = {
                "connected_at": datetime.utcnow().isoformat(),
                "user_info": user_info or {},
                "last_ping": datetime.utcnow().isoformat()
            }
            
            logger.info(f"👤 User {user_id} connected to negocio {codigo_negocio}")
            
            # Enviar mensaje de bienvenida
            await self._send_to_user(user_id, codigo_negocio, {
                "type": "connection_established",
                "message": f"Conectado a negocio {codigo_negocio}",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def disconnect(self, user_id: int, codigo_negocio: str):
        """
        Desconectar usuario de un negocio específico
        
        Args:
            user_id: ID del usuario
            codigo_negocio: Código del negocio
        """
        async with self._lock:
            if (codigo_negocio in self.active_connections and 
                user_id in self.active_connections[codigo_negocio]):
                
                # Remover conexión
                del self.active_connections[codigo_negocio][user_id]
                
                # Remover metadata
                if (codigo_negocio in self.connection_metadata and 
                    user_id in self.connection_metadata[codigo_negocio]):
                    del self.connection_metadata[codigo_negocio][user_id]
                
                # Limpiar negocio si no tiene conexiones
                if not self.active_connections[codigo_negocio]:
                    del self.active_connections[codigo_negocio]
                    if codigo_negocio in self.connection_metadata:
                        del self.connection_metadata[codigo_negocio]
                
                logger.info(f"👤 User {user_id} disconnected from negocio {codigo_negocio}")
    
    async def notify_negocio_changes(self, codigo_negocio: str, change_data: Dict):
        """
        Notificar cambios a todos los usuarios de un negocio
        
        Args:
            codigo_negocio: Código del negocio
            change_data: Datos del cambio
        """
        if codigo_negocio not in self.active_connections:
            logger.debug(f"No active connections for negocio {codigo_negocio}")
            return
        
        connections = self.active_connections[codigo_negocio].copy()
        
        message = {
            "type": "negocio_update",
            "codigo_negocio": codigo_negocio,
            "data": change_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Enviar a todos los usuarios del negocio
        disconnected_users = []
        
        for user_id, websocket in connections.items():
            try:
                await websocket.send_text(json.dumps(message))
                logger.debug(f"📡 Sent update to user {user_id} in negocio {codigo_negocio}")
                
            except Exception as e:
                logger.warning(f"Failed to send message to user {user_id}: {e}")
                disconnected_users.append(user_id)
        
        # Limpiar conexiones muertas
        for user_id in disconnected_users:
            await self.disconnect(user_id, codigo_negocio)
        
        logger.info(f"📡 Notified {len(connections) - len(disconnected_users)} users in negocio {codigo_negocio}")
    
    async def _send_to_user(self, user_id: int, codigo_negocio: str, message: Dict):
        """Enviar mensaje a usuario específico"""
        try:
            if (codigo_negocio in self.active_connections and 
                user_id in self.active_connections[codigo_negocio]):
                
                websocket = self.active_connections[codigo_negocio][user_id]
                await websocket.send_text(json.dumps(message))
                
        except Exception as e:
            logger.warning(f"Failed to send message to user {user_id}: {e}")
            await self.disconnect(user_id, codigo_negocio)
    
    async def send_ping_to_all(self):
        """Enviar ping a todas las conexiones para mantenerlas vivas"""
        ping_message = {
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        disconnected = []
        total_sent = 0
        
        for codigo_negocio, connections in self.active_connections.items():
            for user_id, websocket in connections.items():
                try:
                    await websocket.send_text(json.dumps(ping_message))
                    total_sent += 1
                    
                    # Actualizar last_ping
                    if codigo_negocio in self.connection_metadata:
                        if user_id in self.connection_metadata[codigo_negocio]:
                            self.connection_metadata[codigo_negocio][user_id]["last_ping"] = datetime.utcnow().isoformat()
                
                except Exception as e:
                    logger.warning(f"Ping failed to user {user_id}: {e}")
                    disconnected.append((user_id, codigo_negocio))
        
        # Limpiar conexiones muertas
        for user_id, codigo_negocio in disconnected:
            await self.disconnect(user_id, codigo_negocio)
        
        logger.debug(f"📡 Sent ping to {total_sent} connections, cleaned {len(disconnected)} dead connections")
    
    def get_active_connections_stats(self) -> Dict:
        """Obtener estadísticas de conexiones activas"""
        stats = {
            "total_negocios": len(self.active_connections),
            "total_connections": 0,
            "negocios_detail": {}
        }
        
        for codigo_negocio, connections in self.active_connections.items():
            user_count = len(connections)
            stats["total_connections"] += user_count
            
            stats["negocios_detail"][codigo_negocio] = {
                "active_users": user_count,
                "user_ids": list(connections.keys())
            }
        
        return stats
    
    def get_negocio_connections(self, codigo_negocio: str) -> List[int]:
        """Obtener lista de user_ids conectados a un negocio"""
        if codigo_negocio in self.active_connections:
            return list(self.active_connections[codigo_negocio].keys())
        return []
    
    def is_user_connected(self, user_id: int, codigo_negocio: str) -> bool:
        """Verificar si un usuario está conectado a un negocio"""
        return (codigo_negocio in self.active_connections and 
                user_id in self.active_connections[codigo_negocio])
    
    async def handle_client_message(self, user_id: int, codigo_negocio: str, message: Dict):
        """
        Manejar mensajes desde el cliente
        
        Args:
            user_id: ID del usuario
            codigo_negocio: Código del negocio
            message: Mensaje del cliente
        """
        try:
            message_type = message.get("type")
            
            if message_type == "pong":
                # Respuesta a ping
                if codigo_negocio in self.connection_metadata:
                    if user_id in self.connection_metadata[codigo_negocio]:
                        self.connection_metadata[codigo_negocio][user_id]["last_ping"] = datetime.utcnow().isoformat()
            
            elif message_type == "request_refresh":
                # Cliente solicita datos actualizados
                response = {
                    "type": "refresh_requested",
                    "message": "Refresh signal received, updating data...",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self._send_to_user(user_id, codigo_negocio, response)
            
            else:
                logger.warning(f"Unknown message type from user {user_id}: {message_type}")
        
        except Exception as e:
            logger.error(f"Error handling client message: {e}")

# Instancia global del manager
websocket_manager = WebSocketManager()