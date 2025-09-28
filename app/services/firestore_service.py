# ==========================================
# app/services/firestore_service.py - Servicio para Firestore
# ==========================================

"""Servicio para operaciones con Firestore"""
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class FirestoreService:
    """Servicio para interactuar con Firestore"""
    
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Inicializar Firebase Admin SDK"""
        try:
            # Verificar si ya está inicializado
            if firebase_admin._apps:
                self.db = firestore.client()
                return
            
            # Configurar credenciales desde variable de entorno o archivo
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "credentials/firebase-credentials.json")
            
            if os.path.exists(cred_path):
                # Desde archivo JSON
                cred = credentials.Certificate(cred_path)
            else:
                # Desde variable de entorno JSON
                import json
                cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
                if cred_json:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                else:
                    # Usar credenciales por defecto de Google Cloud
                    cred = credentials.ApplicationDefault()
            
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            
            logger.info("✅ Firebase Firestore initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Error initializing Firebase: {e}")
            raise
    
    # ==========================================
    # OPERACIONES BÁSICAS DE SOLICITUDES
    # ==========================================
    
    async def get_solicitudes_by_negocio(
        self, 
        codigo_negocio: str, 
        limit: int = 50,
        last_doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtener solicitudes por código de negocio con paginación
        
        Args:
            codigo_negocio: Código del negocio
            limit: Límite de registros
            last_doc_id: ID del último documento para paginación
            
        Returns:
            Dict con solicitudes y metadata
        """
        try:
            collection_ref = self.db.collection("citas")
            query = collection_ref.where("codigo_negocio", "==", codigo_negocio)
            
            # Ordenar por fecha de creación
            query = query.order_by("fecha_creacion", direction=firestore.Query.DESCENDING)
            
            # Paginación
            if last_doc_id:
                last_doc = collection_ref.document(last_doc_id).get()
                if last_doc.exists:
                    query = query.start_after(last_doc)
            
            # Aplicar límite
            query = query.limit(limit)
            
            # Ejecutar consulta
            docs = query.stream()
            
            solicitudes = []
            last_document = None
            
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                solicitudes.append(data)
                last_document = doc
            
            # Obtener conteo total (para metadata)
            total_count = await self.count_solicitudes_by_negocio(codigo_negocio)
            
            return {
                "solicitudes": solicitudes,
                "total_count": total_count,
                "returned_count": len(solicitudes),
                "last_doc_id": last_document.id if last_document else None,
                "has_more": len(solicitudes) == limit,
                "codigo_negocio": codigo_negocio,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting solicitudes for negocio {codigo_negocio}: {e}")
            raise
    
    async def get_solicitud_by_id(self, solicitud_id: str) -> Optional[Dict[str, Any]]:
        """Obtener solicitud por ID"""
        try:
            doc_ref = self.db.collection("solicitudes").document(solicitud_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting solicitud {solicitud_id}: {e}")
            raise
    
    async def update_solicitud(
        self, 
        solicitud_id: str, 
        update_data: Dict[str, Any]
    ) -> bool:
        """
        Actualizar solicitud por ID
        
        Args:
            solicitud_id: ID de la solicitud
            update_data: Datos a actualizar
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            # Agregar timestamp de actualización
            update_data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.db.collection("solicitudes").document(solicitud_id)
            doc_ref.update(update_data)
            
            logger.info(f"Solicitud {solicitud_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error updating solicitud {solicitud_id}: {e}")
            raise
    
    async def create_solicitud(self, solicitud_data: Dict[str, Any]) -> str:
        """
        Crear nueva solicitud
        
        Args:
            solicitud_data: Datos de la solicitud
            
        Returns:
            ID del documento creado
        """
        try:
            # Agregar timestamps
            solicitud_data['created_at'] = firestore.SERVER_TIMESTAMP
            solicitud_data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.db.collection("solicitudes").add(solicitud_data)
            doc_id = doc_ref[1].id
            
            logger.info(f"Solicitud created with ID: {doc_id}")
            return doc_id
            
        except Exception as e:
            logger.error(f"Error creating solicitud: {e}")
            raise
    
    async def delete_solicitud(self, solicitud_id: str) -> bool:
        """Eliminar solicitud por ID (soft delete)"""
        try:
            update_data = {
                'deleted': True,
                'deleted_at': firestore.SERVER_TIMESTAMP
            }
            
            doc_ref = self.db.collection("solicitudes").document(solicitud_id)
            doc_ref.update(update_data)
            
            logger.info(f"Solicitud {solicitud_id} marked as deleted")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting solicitud {solicitud_id}: {e}")
            raise
    
    # ==========================================
    # OPERACIONES PARA EL WORKER DE MONITOREO
    # ==========================================
    
    async def count_solicitudes_by_negocio(self, codigo_negocio: str) -> int:
        """
        Contar solicitudes activas por negocio (para el worker)
        
        Args:
            codigo_negocio: Código del negocio
            
        Returns:
            Número de solicitudes activas
        """
        try:
            today = datetime.today().strftime("%d/%m/%Y")
            query = self.db.collection("citas") \
            .where("codigo_negocio", "==", codigo_negocio) \
            .where("fecha", "==", today.isoformat()) \
            .where("estado", "in", ["pendiente", "confirmada"])  # Solo estos estados
            
            # Usar aggregation query para contar (más eficiente)
            from google.cloud.firestore_v1.base_query import FieldFilter
            from google.cloud.firestore_v1.aggregation import AggregationQuery
            
            aggregate_query = AggregationQuery(query)
            result = aggregate_query.count().get()
            
            count = result[0].value
            logger.debug(f"Count for negocio {codigo_negocio}: {count}")
            
            return count
            
        except Exception as e:
            logger.warning(f"Error counting solicitudes for {codigo_negocio}, using fallback: {e}")
            
            # Fallback: contar manualmente
            try:
                docs = query.stream()
                count = sum(1 for _ in docs)
                return count
            except Exception as fallback_error:
                logger.error(f"Fallback count also failed: {fallback_error}")
                return 0
    
    async def get_all_active_negocios(self) -> List[str]:
        """
        Obtener todos los códigos de negocio activos
        
        Returns:
            Lista de códigos de negocio únicos
        """
        try:
            # Obtener valores únicos de codigo_negocio
            query = self.db.collection("negocios").where("estado", "==", True)
            
            docs = query.stream()
            negocios = set()
            
            for doc in docs:
                logger.info(f"Negocio ID: {doc.id}, Data: {doc.to_dict()}")
                codigo_negocio = doc.id             
                if codigo_negocio:
                    negocios.add(codigo_negocio)

            # Imprimir el contenido de negocios
            logger.info(f"Negocios encontrados: {list(negocios)}")
            logger.info(f"Total de negocios: {len(negocios)}")
            
            return list(negocios)
            
        except Exception as e:
            logger.error(f"Error getting active negocios: {e}")
            return []
    
    async def get_counts_for_all_negocios(self) -> Dict[str, int]:
        """
        Obtener conteos para todos los negocios activos
        
        Returns:
            Dict con codigo_negocio -> count
        """
        try:
            negocios = await self.get_all_active_negocios()
            counts = {}
            
            for negocio in negocios:
                count = await self.count_solicitudes_by_negocio(negocio)
                counts[negocio] = count
            
            logger.debug(f"All negocios counts: {counts}")
            return counts
            
        except Exception as e:
            logger.error(f"Error getting counts for all negocios: {e}")
            return {}
    
    # ==========================================
    # OPERACIONES ADICIONALES
    # ==========================================
    
    async def search_solicitudes(
        self, 
        codigo_negocio: str,
        filters: Dict[str, Any] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Buscar solicitudes con filtros
        
        Args:
            codigo_negocio: Código del negocio
            filters: Filtros adicionales
            limit: Límite de resultados
            
        Returns:
            Lista de solicitudes
        """
        try:
            query = self.db.collection("solicitudes").where("codigo_negocio", "==", codigo_negocio)
            query = query.where("deleted", "==", False)
            
            # Aplicar filtros adicionales
            if filters:
                for field, value in filters.items():
                    if field in ['status', 'tipo', 'prioridad']:  # Campos permitidos
                        query = query.where(field, "==", value)
            
            query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
            query = query.limit(limit)
            
            docs = query.stream()
            
            solicitudes = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                solicitudes.append(data)
            
            return solicitudes
            
        except Exception as e:
            logger.error(f"Error searching solicitudes: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar conexión con Firestore"""
        try:
            # Intentar leer un documento pequeño
            test_doc = self.db.collection("_health").document("test").get()
            
            return {
                "status": "healthy",
                "firestore_connected": True,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Firestore health check failed: {e}")
            return {
                "status": "error",
                "firestore_connected": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }