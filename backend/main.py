"""
AI Compass — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import health, models, routing, evaluation, auth

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Adaptive Risk-Aware Multi-Objective AI Model Routing System",
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
app.include_router(routing.router, prefix="/api/v1", tags=["routing"])
app.include_router(evaluation.router, prefix="/api/v1", tags=["evaluation"])
