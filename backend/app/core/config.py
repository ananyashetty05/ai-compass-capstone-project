"""
AI Compass - Core Configuration
"""
import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Compass"
    APP_VERSION: str = "1.0.0"

    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    MAX_ESCALATION_ATTEMPTS: int = 2
    PROVIDER_TIMEOUT_SECONDS: float = 30.0
    QUALITY_ACCEPTANCE_THRESHOLD: float = 0.55
    RISK_ACCEPTANCE_THRESHOLD: float = 0.80

    # Real LLM API keys — set in .env
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    # Comma-separated provider names, e.g. "openai" during a billing outage.
    DISABLED_PROVIDERS: str = ""

    # JWT
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # PostgreSQL database URL (Neon)
    DATABASE_URL: str = ""
    # Test-only Neon branch/database. Never falls back to DATABASE_URL in tests.
    TEST_DATABASE_URL: str = ""

    # SQLite path retained for migration/backup
    DB_PATH: str = os.path.join(
        os.path.dirname(__file__), "../../../aicompass.db"
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
