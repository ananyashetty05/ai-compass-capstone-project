"""
AI Compass - Core Configuration
"""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve backend/.env relative to this file, so it loads regardless of the
# directory uvicorn is started from.
_ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


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
    # Enable only after the approved live-registry migration is applied.
    LIVE_REGISTRY_ENABLED: bool = False
    # Autonomous model catalogue. Persistence needs the approved migration 20261121_model_catalog.sql; without it
    # the app serves the offline seed catalogue exactly as before.
    CATALOG_PERSISTENCE_ENABLED: bool = False
    # Bearer secret Vercel Cron sends to /api/catalog/cron. Empty = the cron endpoint is disabled.
    CRON_SECRET: str = ""
    CATALOG_REFRESH_TIME_BUDGET_SECONDS: float = 45.0
    # Seconds a process keeps its cached view before checking the store version again.
    CATALOG_CACHE_SECONDS: int = 30
    # Shared secret for registry refresh/verification endpoints. Empty = disabled.
    REGISTRY_ADMIN_TOKEN: str = ""
    # A provider catalog younger than this is "fresh"; refresh(only_if_stale) skips it.
    REGISTRY_REFRESH_TTL_MINUTES: int = 360
    # Consecutive successful provider lists that omit a model before it becomes "unavailable".
    REGISTRY_MISSING_REFRESHES_BEFORE_UNAVAILABLE: int = 2
    # A successful inference verification older than this no longer admits a live-only model.
    REGISTRY_VERIFICATION_MAX_AGE_DAYS: int = 14
    # Minimum seconds between verification calls for the same model (cost/abuse guard).
    REGISTRY_VERIFICATION_COOLDOWN_SECONDS: int = 600

    # SQLite path retained for migration/backup
    DB_PATH: str = os.path.join(
        os.path.dirname(__file__), "../../../aicompass.db"
    )
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


settings = Settings()
