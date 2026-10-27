from typing import List, Union
import json
import secrets
from pydantic import field_validator, model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "MSFinanças"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1, le=1440)  # 1 hour
    
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/msfinancas"
    
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000"
    ]
    
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_FROM: str = ""
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    PASSWORD_RESET_URL: str = ""

    PORT: int = 8001
    ENVIRONMENT: str = Field(default="development", pattern="^(development|test|staging|production)$")

    @model_validator(mode="after")
    def production_security(self):
        if self.ALGORITHM != "HS256":
            raise ValueError("Apenas HS256 é permitido")
        if self.ENVIRONMENT in ("production", "staging"):
            if "SECRET_KEY" not in self.model_fields_set or len(self.SECRET_KEY) < 32 or self.SECRET_KEY.startswith("change-this"):
                raise ValueError("Produção exige SECRET_KEY aleatória com pelo menos 32 caracteres")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Produção exige origens CORS explícitas")
        return self

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    return json.loads(v_str)
                except Exception:
                    pass
            return [origin.strip() for origin in v_str.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
