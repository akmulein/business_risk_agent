from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from counterparty_verification.domain import MAX_BATCH_INNS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Counterparty Verification API"
    openrouter_api_key: str | None = None
    openrouter_model: str = "~deepseek/deepseek-v4-flash-latest"

    mcp_url: str = "http://localhost:8001/mcp"
    session_ttl_seconds: int = Field(default=3600, gt=0)
    chat_history_limit: int = Field(default=12, ge=0, le=50)
    chat_max_tokens: int = Field(default=2048, ge=128, le=8192)

    # How many companies in a batch may collect their MCP chapters at once.
    # Chapter tool calls are cheap in-memory computation over a reused MCP
    # connection, so this can cover a whole batch.
    batch_chapter_concurrency: int = Field(default=MAX_BATCH_INNS, ge=1)
    # How many OpenRouter calls (per-company summaries + the comparison
    # summary) may be in flight at once; bounded by the upstream rate limit.
    batch_llm_concurrency: int = Field(default=3, ge=1)

    repository_backend: str = "mongo"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/counterparties"
    )
    mongodb_url: str = (
        "mongodb://contractors_admin:change_me@localhost:27017/"
        "counterparties?authSource=admin"
    )
    mongodb_database: str = "counterparties"
    mongodb_collection: str = "counterparty_cards"
    mongodb_source_collection: str = "reports"
    mongodb_chat_collection: str = "chat_sessions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
