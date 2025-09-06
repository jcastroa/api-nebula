# ==========================================
# app/crud/base.py - CRUD base abstracto
# ==========================================

"""CRUD base con operaciones comunes"""
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from abc import ABC, abstractmethod

ModelType = TypeVar("ModelType")

class BaseCRUD(Generic[ModelType], ABC):
    """Clase base abstracta para operaciones CRUD"""
    
    def __init__(self, model: Type[ModelType] = None):
        self.model = model
    
    @abstractmethod
    async def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Obtener registro por ID"""
        pass
    
    @abstractmethod
    async def get_multi(
        self, 
        skip: int = 0, 
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Obtener múltiples registros con filtros"""
        pass
    
    @abstractmethod
    async def create(self, obj_in: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear nuevo registro"""
        pass
    
    @abstractmethod
    async def update(
        self, 
        id: int, 
        obj_in: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Actualizar registro existente"""
        pass
    
    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Eliminar registro"""
        pass
    
    @abstractmethod
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Contar registros con filtros"""
        pass