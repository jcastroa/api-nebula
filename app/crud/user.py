# ==========================================
# app/crud/user.py - CRUD de usuarios
# ==========================================

"""CRUD operations para la tabla users"""
from typing import Optional, List, Dict, Any
from app.crud.base import BaseCRUD
from app.core.database import get_db_connection
from app.core.security import hash_password
import logging

logger = logging.getLogger(__name__)

class UserCRUD(BaseCRUD):
    """CRUD específico para usuarios"""
    
    def __init__(self):
        super().__init__(None)  # No usamos modelo ORM
    
    async def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Obtener usuario por ID"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id, username, email, first_name, last_name,
                           is_active, created_at, updated_at, ultimo_consultorio_activo
                    FROM users 
                    WHERE id = %s AND is_active = TRUE
                """, (id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting user {id}: {e}")
            return None
    
    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Obtener usuario por username (incluye password_hash)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id, username, email, password_hash, first_name, last_name,
                           is_active, created_at, updated_at ,rol_global_id, ultimo_consultorio_activo
                    FROM users 
                    WHERE username = %s AND is_active = TRUE
                """, (username.lower().strip(),))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None
    
    # async def get_complete_user_data(
    #     self, 
    #     usuario_id: int,
    #     consultorio_id: Optional[int] = None
    # ) -> Dict[str, Any]:
    #     """
    #     Obtener datos completos del usuario para autenticación
        
    #     Args:
    #         usuario_id: ID del usuario
    #         consultorio_id: ID del consultorio específico (opcional)
            
    #     Returns:
    #         Dict con toda la información del usuario
    #     """
    #     try:
    #         with get_db_connection() as conn:
    #             cursor = conn.cursor(dictionary=True)
                
    #             # 1. Consulta principal del usuario
    #             cursor.execute("""
    #             SELECT 
    #                 u.id as usuario_id,
    #                 u.username,
    #                 u.email,
    #                 u.first_name,
    #                 u.last_name,
    #                 u.is_active,
    #                 u.rol_global_id,
    #                 u.ultimo_consultorio_activo,
                    
    #                 -- Datos del rol global (si existe)
    #                 rg.nombre as rol_global_nombre,
    #                 rg.descripcion as rol_global_descripcion,
                    
    #                 -- Consultorio principal del sistema
    #                 cp.id as consultorio_principal_id,
    #                 cp.nombre as consultorio_principal_nombre,
                    
    #                 -- Último consultorio activo del usuario
    #                 cu.id as ultimo_consultorio_id,
    #                 cu.nombre as ultimo_consultorio_nombre

    #             FROM users u
    #             LEFT JOIN roles rg ON u.rol_global_id = rg.id_rol
    #             LEFT JOIN consultorios cp ON cp.es_principal = 1
    #             LEFT JOIN consultorios cu ON u.ultimo_consultorio_activo = cu.id
    #             WHERE u.id = %s AND u.is_active = 1
    #             """, (usuario_id,))
                
    #             usuario = cursor.fetchone()
    #             if not usuario:
    #                 return None

    #             # 2. Consultorios del usuario
    #             consultorios_usuario = await self.get_user_consultorios(usuario_id)
                
    #             # 3. Todos los consultorios (solo para superadmin)
    #             todos_consultorios = None
    #             if usuario['rol_global_id']:
    #                 todos_consultorios = await self.get_all_consultorios()

    #             # 4. Determinar roles activos
    #             roles_activos = []
    #             if usuario['rol_global_id']:
    #                 roles_activos.append(usuario['rol_global_id'])
                
    #             es_superadmin = usuario['rol_global_id'] is not None
                
    #             if consultorio_id and not es_superadmin:
    #                 consultorio_actual = next((c for c in consultorios_usuario if c['consultorio_id'] == consultorio_id), None)
    #                 if consultorio_actual:
    #                     roles_activos.append(consultorio_actual['rol_id'])
    #             elif not es_superadmin:
    #                 roles_activos.extend([c['rol_id'] for c in consultorios_usuario])

    #             # 5. Módulos según roles activos
    #             if es_superadmin:
    #                 menu_modulos = await self.get_all_modulos()
    #             else:
    #                 menu_modulos = await self.get_user_modulos(roles_activos) if roles_activos else []

    #             # 6. Permisos según roles activos
    #             if es_superadmin:
    #                 permisos_lista = await self.get_all_permisos()
    #             else:
    #                 permisos_lista = await self.get_user_permisos(roles_activos) if roles_activos else []

    #             # Construir respuesta
    #             return {
    #                 "usuario": {
    #                     "id": usuario['usuario_id'],
    #                     "username": usuario['username'],
    #                     "email": usuario['email'],
    #                     "first_name": usuario['first_name'],
    #                     "last_name": usuario['last_name'],
    #                     "is_active": bool(usuario['is_active'])
    #                 },
    #                 "rol_global": {
    #                     "id": usuario['rol_global_id'],
    #                     "nombre": usuario['rol_global_nombre'],
    #                     "descripcion": usuario['rol_global_descripcion']
    #                 } if usuario['rol_global_id'] else None,
    #                 "consultorio_principal": {
    #                     "id": usuario['consultorio_principal_id'],
    #                     "nombre": usuario['consultorio_principal_nombre']
    #                 } if usuario['consultorio_principal_id'] else None,
    #                 "ultimo_consultorio_activo": {
    #                     "id": usuario['ultimo_consultorio_id'],
    #                     "nombre": usuario['ultimo_consultorio_nombre']
    #                 } if usuario['ultimo_consultorio_id'] else None,
    #                 "consultorio_contexto_actual": consultorio_id,
    #                 "consultorios_usuario": consultorios_usuario,
    #                 "todos_consultorios": todos_consultorios,
    #                 "menu_modulos": menu_modulos,
    #                 "permisos_lista": permisos_lista,
    #                 "roles_activos": roles_activos,
    #                 "es_superadmin": es_superadmin
    #             }
                
    #     except Exception as e:
    #         logger.error(f"Error getting complete user data for {usuario_id}: {e}")
    #         return None

    async def get_complete_user_data(
        self, 
        usuario_id: int, 
        consultorio_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtener datos completos del usuario para autenticación
        CORREGIDO: Un solo rol activo por contexto
        
        Args:
            usuario_id: ID del usuario
            consultorio_id: ID del consultorio específico (opcional)
            
        Returns:
            Dict con toda la información del usuario
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                # 1. Consulta principal del usuario
                cursor.execute("""
                SELECT 
                    u.id as usuario_id,
                    u.username,
                    u.email,
                    u.first_name,
                    u.last_name,
                    u.is_active,
                    u.rol_global_id,
                    u.ultimo_consultorio_activo,
                    
                    -- Datos del rol global (si existe)
                    rg.nombre as rol_global_nombre,
                    rg.descripcion as rol_global_descripcion,
                    
                    -- Consultorio principal del sistema
                    cp.id as consultorio_principal_id,
                    cp.nombre as consultorio_principal_nombre,
                    
                    -- Último consultorio activo del usuario
                    cu.id as ultimo_consultorio_id,
                    cu.nombre as ultimo_consultorio_nombre

                FROM users u
                LEFT JOIN roles rg ON u.rol_global_id = rg.id_rol
                LEFT JOIN consultorios cp ON cp.es_principal = 1
                LEFT JOIN consultorios cu ON u.ultimo_consultorio_activo = cu.id
                WHERE u.id = %s AND u.is_active = 1
                """, (usuario_id,))
                
                usuario = cursor.fetchone()
                if not usuario:
                    return None

                # 2. Consultorios del usuario
                consultorios_usuario = await self.get_user_consultorios(usuario_id)
                
                # 3. Todos los consultorios (solo para superadmin)
                todos_consultorios = None
                es_superadmin = usuario['rol_global_id'] == 1  # Asumiendo que 1 es superadmin
                
                if es_superadmin:
                    todos_consultorios = await self.get_all_consultorios()

                # 4. DETERMINAR ROL ACTIVO ÚNICO
                rol_activo = None
                consultorio_contexto_actual = consultorio_id
                
                if es_superadmin:
                    # Superadmin ve todo
                    menu_modulos = await self.get_all_modulos()
                    permisos_lista = await self.get_all_permisos()
                    rol_activo = usuario['rol_global_id']
                    
                else:
                    # Usuario normal: UN solo rol según contexto
                    if consultorio_id is None:
                        # Login inicial: usar consultorio principal del usuario
                        consultorio_principal_usuario = next(
                            (c for c in consultorios_usuario if c['es_principal']), 
                            consultorios_usuario[0] if consultorios_usuario else None
                        )
                        
                        if consultorio_principal_usuario:
                            rol_activo = consultorio_principal_usuario['rol_id']
                            consultorio_contexto_actual = consultorio_principal_usuario['consultorio_id']
                        else:
                            # Sin consultorios asignados, usar rol global si existe
                            rol_activo = usuario['rol_global_id']
                            
                    else:
                        # Consultorio específico: usar rol de ese consultorio
                        consultorio_actual = next(
                            (c for c in consultorios_usuario if c['consultorio_id'] == consultorio_id), 
                            None
                        )
                        
                        if consultorio_actual:
                            rol_activo = consultorio_actual['rol_id']
                        else:
                            # Sin acceso al consultorio solicitado, usar rol global
                            rol_activo = usuario['rol_global_id']
                    
                    # Obtener módulos y permisos para EL rol activo únicamente
                    if rol_activo:
                        menu_modulos = await self.get_user_modulos(rol_activo)
                        permisos_lista = await self.get_user_permisos(rol_activo)
                    else:
                        menu_modulos = []
                        permisos_lista = []

                # Construir respuesta
                return {
                    "usuario": {
                        "id": usuario['usuario_id'],
                        "username": usuario['username'],
                        "email": usuario['email'],
                        "first_name": usuario['first_name'],
                        "last_name": usuario['last_name'],
                        "is_active": bool(usuario['is_active'])
                    },
                    "rol_global": {
                        "id": usuario['rol_global_id'],
                        "nombre": usuario['rol_global_nombre'],
                        "descripcion": usuario['rol_global_descripcion']
                    } if usuario['rol_global_id'] else None,
                    "consultorio_principal": {
                        "id": usuario['consultorio_principal_id'],
                        "nombre": usuario['consultorio_principal_nombre']
                    } if usuario['consultorio_principal_id'] else None,
                    "ultimo_consultorio_activo": {
                        "id": usuario['ultimo_consultorio_id'],
                        "nombre": usuario['ultimo_consultorio_nombre']
                    } if usuario['ultimo_consultorio_id'] else None,
                    "consultorio_contexto_actual": consultorio_contexto_actual,
                    "consultorios_usuario": consultorios_usuario,
                    "todos_consultorios": todos_consultorios,
                    "menu_modulos": menu_modulos,
                    "permisos_lista": permisos_lista,
                    "rol_activo": rol_activo,  # UN SOLO ROL
                    "es_superadmin": es_superadmin
                }
                
        except Exception as e:
            logger.error(f"Error getting complete user data for {usuario_id}: {e}")
            return None
    
    async def get_user_consultorios(self, usuario_id: int) -> List[Dict[str, Any]]:
        """Obtener consultorios del usuario con sus roles"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                SELECT 
                    c.id as consultorio_id,
                    c.nombre,
                    COALESCE(c.ruc, '') as ruc,
                    COALESCE(c.direccion, '') as direccion,
                    COALESCE(c.telefono, '') as telefono,
                    COALESCE(c.email, '') as email,
                    c.estado,
                    uc.rol_id,
                    r.nombre as rol_nombre,
                    COALESCE(r.descripcion, '') as rol_descripcion,
                    uc.es_principal,
                    uc.estado as estado_asignacion,
                    COALESCE(uc.fecha_inicio, '') as fecha_inicio,
                    COALESCE(uc.fecha_fin, '') as fecha_fin
                FROM usuario_consultorios uc
                INNER JOIN consultorios c ON uc.consultorio_id = c.id
                INNER JOIN roles r ON uc.rol_id = r.id_rol
                WHERE uc.usuario_id = %s 
                AND uc.estado = 'activo'
                AND c.estado = 'activo'
                ORDER BY uc.es_principal DESC, c.nombre
                """, (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting user consultorios for {usuario_id}: {e}")
            return []

    async def get_all_consultorios(self) -> List[Dict[str, Any]]:
        """Obtener todos los consultorios (para superadmin)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                SELECT 
                    id as consultorio_id,
                    nombre,
                    COALESCE(ruc, '') as ruc,
                    COALESCE(direccion, '') as direccion,
                    COALESCE(telefono, '') as telefono,
                    COALESCE(email, '') as email,
                    estado,
                    es_principal
                FROM consultorios 
                WHERE estado IN ('activo', 'configurando')
                ORDER BY es_principal DESC, nombre
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting all consultorios: {e}")
            return []

    async def get_all_modulos(self) -> List[Dict[str, Any]]:
        """Obtener todos los módulos (para superadmin)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                SELECT 
                    id_modulo as modulo_id,
                    nombre,
                    COALESCE(descripcion, '') as descripcion,
                    COALESCE(ruta, '') as ruta,
                    COALESCE(icono, '') as icono,
                    orden,
                    modulo_padre_id
                FROM modulos 
                WHERE activo = 1
                ORDER BY orden, nombre
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting all modules: {e}")
            return []


    async def get_user_modulos(self, rol_id: int) -> List[Dict[str, Any]]:
        """
        Obtener módulos según UN rol específico del usuario
        
        Args:
            rol_id: ID del rol específico (no una lista)
            
        Returns:
            Lista de módulos disponibles para ese rol
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                SELECT DISTINCT
                    m.id_modulo as modulo_id,
                    m.nombre,
                    COALESCE(m.descripcion, '') as descripcion,
                    COALESCE(m.ruta, '') as ruta,
                    COALESCE(m.icono, '') as icono,
                    m.orden,
                    m.modulo_padre_id
                FROM modulos m
                INNER JOIN permisos p ON m.id_modulo = p.id_modulo
                INNER JOIN roles_permisos rp ON p.id_permiso = rp.id_permiso
                WHERE m.activo = 1
                AND p.activo = 1
                AND rp.id_rol = %s
                ORDER BY m.orden, m.nombre
                """, (rol_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting modules for role {rol_id}: {e}")
            return []

    async def get_all_permisos(self) -> List[str]:
        """Obtener todos los permisos (para superadmin)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT CONCAT(m.nombre, ':', a.codigo) as permiso
                FROM modulos m
                INNER JOIN permisos p ON m.id_modulo = p.id_modulo
                INNER JOIN acciones a ON p.id_accion = a.id_accion
                WHERE m.activo = 1
                AND p.activo = 1
                AND a.activo = 1
                """)
                result = cursor.fetchall()
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting all permissions: {e}")
            return []

    async def get_user_permisos(self, rol_id: int) -> List[str]:
        """
        Obtener permisos según UN rol específico del usuario
        
        Args:
            rol_id: ID del rol específico (no una lista)
            
        Returns:
            Lista de permisos en formato "modulo:accion"
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT DISTINCT CONCAT(m.nombre, ':', a.codigo) as permiso
                FROM modulos m
                INNER JOIN permisos p ON m.id_modulo = p.id_modulo
                INNER JOIN acciones a ON p.id_accion = a.id_accion
                INNER JOIN roles_permisos rp ON p.id_permiso = rp.id_permiso
                WHERE m.activo = 1
                AND p.activo = 1
                AND a.activo = 1
                AND rp.id_rol = %s
                """, (rol_id,))
                result = cursor.fetchall()
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting permissions for role {rol_id}: {e}")
            return []
        
    async def update_ultimo_consultorio_activo(self, usuario_id: int, consultorio_id: int) -> bool:
        """Actualizar último consultorio activo del usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET ultimo_consultorio_activo = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (consultorio_id, usuario_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating ultimo_consultorio_activo for user {usuario_id}: {e}")
            return False
        
    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Obtener usuario por email"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id, username, email, first_name, last_name,
                           is_active, created_at, updated_at
                    FROM users 
                    WHERE email = %s AND is_active = TRUE
                """, (email.lower().strip(),))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None
    
    async def get_multi(
        self, 
        skip: int = 0, 
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Obtener múltiples usuarios con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                # Query base
                query = """
                    SELECT id, username, email, first_name, last_name,
                           is_active, created_at, updated_at
                    FROM users 
                    WHERE is_active = TRUE
                """
                params = []
                
                # Aplicar filtros
                if filters:
                    if filters.get('is_admin') is not None:
                        query += " AND is_admin = %s"
                        params.append(filters['is_admin'])
                    
                    if filters.get('search'):
                        search_term = f"%{filters['search']}%"
                        query += " AND (username LIKE %s OR email LIKE %s OR first_name LIKE %s OR last_name LIKE %s)"
                        params.extend([search_term, search_term, search_term, search_term])
                
                # Ordenar y paginar
                query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, skip])
                
                cursor.execute(query, params)
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
    
    async def create(self, obj_in: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear nuevo usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Hash de la contraseña
                password_hash = hash_password(obj_in['password'])
                
                # Insertar usuario
                cursor.execute("""
                    INSERT INTO users 
                    (username, email, password_hash, first_name, last_name, is_admin)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    obj_in['username'].lower().strip(),
                    obj_in['email'].lower().strip(),
                    password_hash,
                    obj_in.get('first_name'),
                    obj_in.get('last_name'),
                    obj_in.get('is_admin', False)
                ))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                # Retornar el usuario creado (sin password)
                return await self.get(user_id)
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None
    
    async def update(
        self, 
        id: int, 
        obj_in: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Actualizar usuario existente"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Construir query dinámicamente
                fields = []
                params = []
                
                # Campos actualizables
                updateable_fields = ['email', 'first_name', 'last_name', 'is_active', 'is_admin']
                
                for field in updateable_fields:
                    if field in obj_in and obj_in[field] is not None:
                        if field == 'email':
                            fields.append(f"{field} = %s")
                            params.append(obj_in[field].lower().strip())
                        elif field in ['first_name', 'last_name']:
                            fields.append(f"{field} = %s")
                            params.append(obj_in[field].strip().title() if obj_in[field] else None)
                        else:
                            fields.append(f"{field} = %s")
                            params.append(obj_in[field])
                
                if not fields:
                    # No hay campos para actualizar
                    return await self.get(id)
                
                # Actualizar timestamp
                fields.append("updated_at = CURRENT_TIMESTAMP")
                
                # Ejecutar update
                query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
                params.append(id)
                
                cursor.execute(query, params)
                conn.commit()
                
                if cursor.rowcount > 0:
                    return await self.get(id)
                
                return None
                
        except Exception as e:
            logger.error(f"Error updating user {id}: {e}")
            return None
    
    async def delete(self, id: int) -> bool:
        """Eliminar usuario (soft delete)"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting user {id}: {e}")
            return False
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Contar usuarios con filtros"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT COUNT(*) FROM users WHERE is_active = TRUE"
                params = []
                
                if filters:
                    if filters.get('is_admin') is not None:
                        query += " AND is_admin = %s"
                        params.append(filters['is_admin'])
                    
                    if filters.get('search'):
                        search_term = f"%{filters['search']}%"
                        query += " AND (username LIKE %s OR email LIKE %s)"
                        params.extend([search_term, search_term])
                
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            return 0
    
    async def change_password(self, id: int, new_password: str) -> bool:
        """Cambiar contraseña del usuario"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                password_hash = hash_password(new_password)
                cursor.execute("""
                    UPDATE users 
                    SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (password_hash, id))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error changing password for user {id}: {e}")
            return False
    
    async def username_exists(self, username: str, exclude_id: Optional[int] = None) -> bool:
        """Verificar si username ya existe"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT COUNT(*) FROM users WHERE username = %s"
                params = [username.lower().strip()]
                
                if exclude_id:
                    query += " AND id != %s"
                    params.append(exclude_id)
                
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking username exists: {e}")
            return True  # Asumir que existe en caso de error
    
    async def email_exists(self, email: str, exclude_id: Optional[int] = None) -> bool:
        """Verificar si email ya existe"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT COUNT(*) FROM users WHERE email = %s"
                params = [email.lower().strip()]
                
                if exclude_id:
                    query += " AND id != %s"
                    params.append(exclude_id)
                
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking email exists: {e}")
            return True  # Asumir que existe en caso de error