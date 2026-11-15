from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values come from (highest priority first): environment variables, the .env
    file, then the defaults below. Names are case-insensitive, so the field
    `bank_url` is set by the BANK_URL environment variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env also holds variables for other tools (e.g. POSTGRES_USER for
        # docker-compose); ignore them instead of failing.
        extra="ignore",
    )

    app_name: str = "payment-gateway-api"
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] | None = None

    # Acquiring bank (simulator)
    bank_url: str = "http://localhost:8080"
    bank_timeout_seconds: float = Field(default=5.0, gt=0)

    # repr=False: the URL contains the database password.
    database_url: str = Field(
        default="postgresql://gateway:gateway@localhost:5432/payment_gateway",
        repr=False,
    )

    @field_validator("bank_url")
    @classmethod
    def strip_trailing_slash(cls, url: str) -> str:
        return url.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def use_asyncpg_driver(cls, url: str) -> str:
        # Accept plain postgresql:// URLs (as used by docker-compose) and point
        # SQLAlchemy at the async asyncpg driver.
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Use with FastAPI: `Depends(get_settings)`."""
    return Settings()
