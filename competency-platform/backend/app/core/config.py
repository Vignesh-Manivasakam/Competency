"""Application settings using pydantic-settings.

All values are loaded from environment variables or .env file.
Spec reference: §16 Environment Configuration.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every env var in .env.example maps to a field here."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_ENV: str = "development"
    SECRET_KEY: str = "your-jwt-secret-key-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/competency_db"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://postgres:password@localhost:5432/competency_db"
    )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Neo4j ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "your-neo4j-password"

    # --- LLM Providers ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    NVIDIA_API_KEY: str = "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"
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    USE_NVIDIA_NIM: bool = True

    # --- LLM Routing ---
    LLM_PRIMARY: str = "gpt-4o"
    LLM_SECONDARY: str = "gpt-4o-mini"
    LLM_FALLBACK: str = "claude-sonnet-4-6"

    # --- LangSmith ---
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "competency-intelligence-mvp"

    # --- Embeddings ---
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # --- Session Config ---
    MAX_SESSION_INTERACTIONS: int = 25
    SESSION_TIMEOUT_HOURS: int = 24
    MASTERY_CONFIDENCE_THRESHOLD: float = 0.80
    MIN_INTERACTIONS_FOR_MASTERY: int = 3


# Singleton instance — import this everywhere
settings = Settings()
