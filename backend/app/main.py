"""
AI Compass — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import health, models, routing, evaluation, auth, feedback, catalog
from app.core.logging import get_logger

logger = get_logger(__name__)


def _warm_in_background() -> None:
    """Open database connections and load the catalogue and live registry ahead of the first request (non-blocking, best effort)."""
    import threading

    def work():
        try:
            if settings.DATABASE_URL:
                from psycopg.rows import dict_row
                from app.core import db
                db.prewarm(settings.DATABASE_URL, 3, row_factory=dict_row)
            from app.services.catalog import registry as catalog_registry
            catalog_registry.warm()
            from app.services import registry_service
            registry_service.live_state()
        except Exception:
            logger.warning("Warm-up skipped; the first request will load these instead.")
    threading.Thread(target=work, name="startup-warm", daemon=True).start()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise persistence once, without making docs/health import-dependent."""
    if settings.DATABASE_URL:
        try:
            from app.services import user_store, feedback_store
            user_store.init_db()
            feedback_store.init_feedback_db()
        except Exception:
            logger.exception("Database initialisation failed; database-backed endpoints are unavailable.")
    else:
        logger.warning("DATABASE_URL is not configured; database-backed endpoints are unavailable.")
    _warm_in_background()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Adaptive Risk-Aware Multi-Objective AI Model Routing System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth & profile"])
app.include_router(models.router, prefix="/api/v1", tags=["models"])
app.include_router(catalog.router, prefix="/api/v1", tags=["catalogue"])
app.include_router(routing.router, prefix="/api/v1", tags=["routing"])
app.include_router(evaluation.router, prefix="/api/v1", tags=["evaluation"])
app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])
