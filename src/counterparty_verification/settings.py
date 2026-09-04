from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Counterparty Verification API"
    openrouter_api_key: str | None = None
    openrouter_model: str = "qwen/qwen3-30b-a3b-instruct-2507"

    mcp_url: str = "http://localhost:8001/mcp"
    mcp_timeout_seconds: float = Field(default=30, gt=0)
    analysis_timeout_seconds: float = Field(default=90, gt=0)
    session_ttl_seconds: int = Field(default=3600, gt=0)

    repository_backend: str = "mock"
    mock_data_path: Path = Path("data/counterparties.json")
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/counterparties"
    )
    mongodb_url: str = (
        "mongodb://contractors_admin:change_me@localhost:27017/"
        "counterparties?authSource=admin"
    )
    mongodb_database: str = "counterparties"
    mongodb_collection: str = "counterparty_cards"


@lru_cache
def get_settings() -> Settings:
    return Settings()
