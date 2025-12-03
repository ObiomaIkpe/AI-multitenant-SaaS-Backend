from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, ClassVar, Dict

class Settings(BaseSettings):
    # Pydantic V2 Configuration for loading from .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8'
    )
    
    # --- Database (Must be defined, as it has no default value)
    DATABASE_URL: str 

    # --- JWT (Must be defined, as it has no default value)
    SECRET_KEY: str 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Celery (Uses default values if not present in .env)
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # --- Qdrant (Uses default values if not present in .env)
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # --- Storage (Uses default values if not present in .env)
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB

    # --- App Settings (Uses default values if not present in .env)
    APP_NAME: str = "Private AI SaaS"
    DEBUG: bool = True

    # --- Ollama Settings
    USE_OLLAMA: bool
    OLLAMA_URL: str

    # --- Email Settings (Mailtrap/SMTP)
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_SERVER: str
    MAIL_PORT: int

    # --- Frontend URL
    FRONTEND_URL: str

    STRIPE_SECRET_KEY: str
    
    
settings = Settings()

class StripeConfig:
    STRIPE_PRICE_IDS: ClassVar[Dict[str, Optional[str]]] = {
        'free': None,
        'managed_cloud': 'price_1SaGf0Elg493txDlQa0FhTzO'
    }

print(settings.STRIPE_SECRET_KEY)
print(StripeConfig.STRIPE_PRICE_IDS['managed_cloud'])
