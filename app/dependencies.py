"""Dependencies comunes para FastAPI"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

from app.services.auth_service import AuthService
from app.crud.user import UserCRUD
from app.crud.session import SessionCRUD
from app.crud.assignment import AssignmentCRUD
from app.crud.role import RoleCRUD

# HTTPBearer para auth
security = HTTPBearer(auto_error=False)

# Singletons
_auth_service = None
_user_crud = None
_session_crud = None
_assignment_crud = None
_role_crud = None

def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service

def get_user_crud() -> UserCRUD:
    global _user_crud
    if _user_crud is None:
        _user_crud = UserCRUD()
    return _user_crud

def get_session_crud() -> SessionCRUD:
    global _session_crud
    if _session_crud is None:
        _session_crud = SessionCRUD()
    return _session_crud

def get_assignment_crud() -> AssignmentCRUD:
    global _assignment_crud
    if _assignment_crud is None:
        _assignment_crud = AssignmentCRUD()
    return _assignment_crud

def get_role_crud() -> RoleCRUD:
    global _role_crud
    if _role_crud is None:
        _role_crud = RoleCRUD()
    return _role_crud

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
    user_crud: UserCRUD = Depends(get_user_crud)
) -> Dict[str, Any]:
    """Obtener usuario actual - prioriza cookies"""
    
    token = None
    
    # 1. Prioridad: Cookie HttpOnly
    if request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    
    # 2. Fallback: Header Authorization  
    elif credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Verificar token y obtener usuario
    payload = await auth_service.verify_access_token(token)
    user = await user_crud.get(payload['user_id'])
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

async def get_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Usuario administrador"""
    if not current_user.get('is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user