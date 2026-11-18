from fastapi import APIRouter
try:
    import psycopg
except ImportError:
    psycopg = None
from app.core.config import settings
router = APIRouter()

@router.get("/health")
def health():
    disabled = {item.strip().lower() for item in settings.DISABLED_PROVIDERS.split(",") if item.strip()}
    database = {"configured": bool(settings.DATABASE_URL), "reachable": False}
    if settings.DATABASE_URL and psycopg is not None:
        try:
            with psycopg.connect(settings.DATABASE_URL, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            database["reachable"] = True
        except Exception:
            database["reachable"] = False
    return {
        "status": "ok" if database["reachable"] else "degraded",
        "service": "AI Compass",
        "database": database,
        "providers": {
            "openai": {"credential_configured": bool(settings.OPENAI_API_KEY), "disabled": "openai" in disabled},
            "anthropic": {"credential_configured": bool(settings.ANTHROPIC_API_KEY), "disabled": "anthropic" in disabled},
            "google": {"credential_configured": bool(settings.GEMINI_API_KEY), "disabled": "google" in disabled},
            "groq": {"credential_configured": bool(settings.GROQ_API_KEY), "disabled": "groq" in disabled},
        },
    }
