# ==========================================
# app/utils/constants.py - Constantes de la aplicación
# ==========================================

"""Constantes utilizadas en toda la aplicación"""

# Estados de usuario
class UserStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"

# Estados de sesión
class SessionStatus:
    ACTIVE = "active"
    INACTIVE = "inactive" 
    EXPIRED = "expired"
    REVOKED = "revoked"

# Tipos de token
class TokenType:
    ACCESS = "access"
    REFRESH = "refresh"

# Niveles de log
class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# Códigos de respuesta HTTP personalizados
class HTTPStatusCode:
    # Éxito
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    
    # Errores de cliente
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    
    # Errores de servidor
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503

# Mensajes de error estándar
class ErrorMessages:
    # Autenticación
    INVALID_CREDENTIALS = "Invalid username or password"
    TOKEN_EXPIRED = "Token has expired"
    TOKEN_INVALID = "Invalid token"
    SESSION_EXPIRED = "Session expired due to inactivity"
    ACCESS_DENIED = "Access denied"
    UNAUTHORIZED = "Authentication required"
    
    # Usuario
    USER_NOT_FOUND = "User not found"
    USER_ALREADY_EXISTS = "User already exists"
    EMAIL_ALREADY_EXISTS = "Email address already in use"
    USERNAME_ALREADY_EXISTS = "Username already taken"
    INVALID_EMAIL_FORMAT = "Invalid email format"
    WEAK_PASSWORD = "Password does not meet security requirements"
    
    # General
    INVALID_INPUT = "Invalid input data"
    RESOURCE_NOT_FOUND = "Resource not found"
    OPERATION_FAILED = "Operation failed"
    INTERNAL_ERROR = "Internal server error"
    RATE_LIMIT_EXCEEDED = "Too many requests"
    
    # Validación
    REQUIRED_FIELD = "This field is required"
    INVALID_FORMAT = "Invalid format"
    VALUE_TOO_SHORT = "Value is too short"
    VALUE_TOO_LONG = "Value is too long"

# Mensajes de éxito
class SuccessMessages:
    # Autenticación
    LOGIN_SUCCESS = "Login successful"
    LOGOUT_SUCCESS = "Logged out successfully" 
    TOKEN_REFRESHED = "Token refreshed successfully"
    PASSWORD_CHANGED = "Password changed successfully"
    
    # Usuario
    USER_CREATED = "User created successfully"
    USER_UPDATED = "User updated successfully"
    USER_DELETED = "User deleted successfully"
    PROFILE_UPDATED = "Profile updated successfully"
    
    # Sesión
    SESSION_REVOKED = "Session revoked successfully"
    ALL_SESSIONS_REVOKED = "All sessions revoked successfully"
    
    # General
    OPERATION_SUCCESS = "Operation completed successfully"
    DATA_SAVED = "Data saved successfully"
    DATA_DELETED = "Data deleted successfully"

# Límites de aplicación
class AppLimits:
    # Usuario
    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 50
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_MAX_LENGTH = 128
    EMAIL_MAX_LENGTH = 100
    NAME_MAX_LENGTH = 50
    
    # Sesión
    MAX_SESSIONS_PER_USER = 10
    SESSION_CLEANUP_HOURS = 6
    
    # Rate limiting
    LOGIN_ATTEMPTS_PER_IP = 5
    LOGIN_ATTEMPTS_WINDOW = 300  # 5 minutos
    
    # Archivos y datos
    MAX_LOG_SIZE_MB = 50
    MAX_BACKUP_FILES = 10
    
    # Paginación
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 1000

# Configuración de cache
class CacheConfig:
    # TTL en segundos
    USER_CACHE_TTL = 3600  # 1 hora
    SESSION_CACHE_TTL = 1800  # 30 minutos
    METRICS_CACHE_TTL = 300  # 5 minutos
    RATE_LIMIT_TTL = 300  # 5 minutos
    
    # Prefijos de clave Redis
    USER_PREFIX = "user:"
    SESSION_PREFIX = "session:"
    BLACKLIST_PREFIX = "blacklist:"
    ACTIVITY_PREFIX = "user_activity:"
    METRIC_PREFIX = "metric:"
    RATE_LIMIT_PREFIX = "rate_limit:"

# Configuración de regex patterns
class RegexPatterns:
    EMAIL = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    USERNAME = r'^[a-zA-Z0-9_-]{3,50}$'
    IPV4 = r'^(\d{1,3}\.){3}\d{1,3}$'
    IPV6 = r'^([0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}$'
    UUID = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    SLUG = r'^[a-z0-9-]+$'

# Headers HTTP personalizados
class CustomHeaders:
    REQUEST_ID = "X-Request-ID"
    PROCESS_TIME = "X-Process-Time"
    RATE_LIMIT_REMAINING = "X-RateLimit-Remaining"
    RATE_LIMIT_RESET = "X-RateLimit-Reset"
    API_VERSION = "X-API-Version"