from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List, Union, Any
from pydantic import field_validator

class Settings(BaseSettings):
    # Database Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "sahyog_setu"
    DATABASE_URL: Optional[str] = None

    # Security Settings
    SECRET_KEY: str = "insecure_default_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_USERNAME: str = "SahyogSyncBot"
    GEMINI_API_KEY: Optional[str] = None
    
    # CORS & Web Linking
    ALLOWED_ORIGINS: Union[List[str], str] = ["https://sahyog-setu-frontend.vercel.app", "http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]
    FRONTEND_URL: str = "https://sahyog-setu-frontend.vercel.app"
    BACKEND_URL: str = "https://sahyogsync.onrender.com"
    
    # Cloudinary Settings
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # Email Settings (Brevo HTTP API)
    BREVO_API_KEY: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: str = "SahyogSync"
    ADMIN_EMAIL: str = "sahyogsync.alerts@gmail.com"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
