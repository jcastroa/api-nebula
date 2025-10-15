"""Configuración de la aplicación usando Pydantic Settings"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List

class Settings(BaseSettings):
    """Configuración centralizada"""
    
    # Aplicación
    APP_NAME: str = "Sistema de Autenticación"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # JWT
    JWT_SECRET_KEY: str = "default-secret-change-me"  # Valor por defecto
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database MySQL
    DB_HOST: str = "mariadb-nebula"  # Cambiado para Docker
    DB_PORT: int = 3306
    DB_USER: str = "auth_user"  # Valor por defecto
    DB_PASSWORD: str = "auth_password_123"  # Valor por defecto
    DB_NAME: str = "nebula"  # Valor por defecto
    DB_POOL_SIZE: int = 10
    
    # Redis
    REDIS_HOST: str = "redis"  # Cambiado para Docker
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    
    # Security
    RECAPTCHA_SECRET_KEY: str = "default-recaptcha-key"  # Valor por defecto
    BCRYPT_ROUNDS: int = 12
    INACTIVITY_TIMEOUT_SECONDS: int = 3600
    
    # CORS - Cambiar a string y parsear
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://tu-frontend.com,https://cita247.com"
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW: int = 300
    
    @field_validator('ALLOWED_ORIGINS')
    @classmethod
    def validate_origins(cls, v):
        """Asegurar que ALLOWED_ORIGINS sea siempre un string"""
        if isinstance(v, list):
            return ','.join(v)
        return str(v)
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Convertir ALLOWED_ORIGINS string a lista para usar en FastAPI"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(',')]
    
    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()