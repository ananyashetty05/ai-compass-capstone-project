"""
AI Compass - Core Configuration
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AI Compass"
    APP_VERSION: str = "1.0.0"

    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    MAX_ESCALATION_ATTEMPTS: int = 2
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

    # SQLite DB path
    DB_PATH: str = os.path.join(os.path.dirname(__file__), "../../../aicompass.db")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

if not settings.JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be configured through the environment.")
