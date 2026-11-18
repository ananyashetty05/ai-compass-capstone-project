"""
Auth & Profile routes — real JWT + SQLite.
"""
import re
import psycopg
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from app.schemas.profile import (
    RegisterRequest, UpdatePreferencesRequest,
    GROUP_DEFAULT_PREFERENCES, GROUP_DESCRIPTIONS,
    AccessibilityPreferences
)
from app.services import user_store

logger = logging.getLogger(__name__)
router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def current_user_id(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[str]:
    if not creds:
        return None
    return user_store.decode_token(creds.credentials)


def require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    uid = current_user_id(creds)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return uid


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def _db_unavailable_message(exc: Exception) -> str:
    if isinstance(exc, RuntimeError) and "DATABASE_URL" in str(exc):
        return "The database is not configured. Set DATABASE_URL in backend/.env and restart the backend."
    return "Cannot reach the database. Check DATABASE_URL and your network, then try again."


def _clean_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    return email


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    user_group: str
    routing_preferences: Optional[dict] = None
    theme_preference: str = "system"


class UpdateProfileBody(BaseModel):
    name: Optional[str] = None
    theme_preference: Optional[str] = None
    accessibility_preferences: Optional[dict] = None


@router.post("/auth/register", status_code=201)
def register(body: RegisterBody):
    from app.schemas.profile import RoutingPreferences
    valid = list(GROUP_DEFAULT_PREFERENCES.keys())
    group = (body.user_group or "").strip().lower()
    if group not in valid:
        raise HTTPException(422, f"user_group must be one of: {valid}")
    name = (body.name or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(422, "Enter your name (up to 100 characters).")
    email = _clean_email(body.email)
    if len(body.password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(body.password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    try:
        prefs = RoutingPreferences(**body.routing_preferences) if body.routing_preferences else None
    except Exception:
        raise HTTPException(422, "Routing preferences must be numbers between 0 and 1.")
    req = RegisterRequest(
        name=name, email=email, user_group=group,
        routing_preferences=prefs, theme_preference=body.theme_preference,
    )
    try:
        profile = user_store.register(req, body.password)
    except user_store.DuplicateEmailError:
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    except (RuntimeError, psycopg.OperationalError) as exc:
        logger.exception("Registration failed: database unavailable")
        raise HTTPException(503, _db_unavailable_message(exc))
    except Exception:
        logger.exception("Registration failed")
        raise HTTPException(500, "Could not create the account. Please try again.")
    token = user_store.create_token(profile.user_id)
    return {"token": token, "profile": profile.model_dump()}


@router.post("/auth/login")
def login(body: LoginRequest):
    email = (body.email or "").strip().lower()
    try:
        profile = user_store.login(email, body.password or "")
    except (RuntimeError, psycopg.OperationalError) as exc:
        logger.exception("Login failed: database unavailable")
        raise HTTPException(503, _db_unavailable_message(exc))
    if not profile:
        raise HTTPException(401, "Invalid email or password")
    token = user_store.create_token(profile.user_id)
    return {"token": token, "profile": profile.model_dump()}


@router.get("/auth/me")
def get_me(uid: str = Depends(require_user)):
    profile = user_store.get_by_id(uid)
    if not profile:
        raise HTTPException(404, "User not found")
    return profile.model_dump()


@router.put("/profile/preferences")
def update_preferences(body: UpdatePreferencesRequest, uid: str = Depends(require_user)):
    updated = user_store.update_preferences(uid, body.routing_preferences)
    if not updated:
        raise HTTPException(404, "User not found")
    return updated.model_dump()


@router.put("/profile")
def update_profile(body: UpdateProfileBody, uid: str = Depends(require_user)):
    acc = AccessibilityPreferences(**body.accessibility_preferences) if body.accessibility_preferences else None
    updated = user_store.update_profile_fields(uid, name=body.name, theme=body.theme_preference, accessibility=acc)
    if not updated:
        raise HTTPException(404, "User not found")
    return updated.model_dump()


@router.get("/profile/group-defaults/{group}")
def group_defaults(group: str):
    g = group.lower()
    d = GROUP_DEFAULT_PREFERENCES.get(g)
    if not d:
        raise HTTPException(404, f"Unknown group: {g}")
    return {"group": g, "description": GROUP_DESCRIPTIONS.get(g, ""), "default_preferences": d}


@router.get("/profile/groups")
def list_groups():
    return [
        {"group": g, "description": GROUP_DESCRIPTIONS.get(g, ""), "defaults": GROUP_DEFAULT_PREFERENCES[g]}
        for g in GROUP_DEFAULT_PREFERENCES
    ]
