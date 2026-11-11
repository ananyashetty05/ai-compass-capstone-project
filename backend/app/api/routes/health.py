from fastapi import APIRouter
from app.core.config import settings
router = APIRouter()

@router.get("/health")
def health():
    disabled = {item.strip().lower() for item in settings.DISABLED_PROVIDERS.split(",") if item.strip()}
    return {
        "status": "ok",
        "service": "AI Compass",
        "providers": {
            "openai": {"credential_configured": bool(settings.OPENAI_API_KEY), "disabled": "openai" in disabled},
            "anthropic": {"credential_configured": bool(settings.ANTHROPIC_API_KEY), "disabled": "anthropic" in disabled},
            "google": {"credential_configured": bool(settings.GEMINI_API_KEY), "disabled": "google" in disabled},
            "groq": {"credential_configured": bool(settings.GROQ_API_KEY), "disabled": "groq" in disabled},
        },
    }
