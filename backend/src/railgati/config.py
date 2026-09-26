"""RailGati application configuration via environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings are prefixed with ``RAILGATI_`` in the environment.
    For example, ``RAILGATI_ENV=production``.
    """

    # Application
    env: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server
    host: str = Field(default="127.0.0.1", description="Backend bind host")
    port: int = Field(default=8000, description="Backend bind port")

    database_url: str = Field(
        default="postgresql+psycopg2://railgati:railgati_dev@localhost:5433/railgati",
        description="PostgreSQL connection URL",
    )

    # CORS
    frontend_origin: str = Field(
        default="http://localhost:3000",
        description="Allowed frontend origin for CORS",
    )

    model_config = {
        "env_prefix": "RAILGATI_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


def get_settings() -> Settings:
    """Create and return application settings."""
    return Settings()
