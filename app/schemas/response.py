# ==========================================
# app/schemas/response.py - Schemas de respuesta generales
# ==========================================

"""Schemas Pydantic para respuestas generales de la API"""
from app.schemas.auth import SessionInfo
from pydantic import BaseModel
from typing import Any, Optional, List, Dict
from datetime import datetime

class SuccessResponse(BaseModel):
    """Respuesta exitosa genérica"""
    success: bool = True
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    """Respuesta de error"""
    success: bool = False
    error: str
    details: Optional[str] = None
    timestamp: datetime = datetime.utcnow()

class HealthResponse(BaseModel):
    """Respuesta del health check"""
    status: str  # "OK" | "ERROR"
    timestamp: datetime
    version: str
    services: Dict[str, str]  # {"mysql": "OK", "redis": "OK"}

class MetricsResponse(BaseModel):
    """Respuesta de métricas del sistema"""
    metrics: Dict[str, int]
    timestamp: datetime

class AdminSessionsResponse(BaseModel):
    """Respuesta del panel de sesiones admin"""
    sessions: List[SessionInfo]
    total: int
    active_count: int