"""
Auth & Profile routes — real JWT + SQLite.
"""
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
    if body.user_group.lower() not in valid:
        raise HTTPException(422, f"user_group must be one of: {valid}")
    try:
        req = RegisterRequest(
            name=body.name,
            email=body.email,
            user_group=body.user_group,
            routing_preferences=RoutingPreferences(**body.routing_preferences) if body.routing_preferences else None,
            theme_preference=body.theme_preference,
        )
        profile = user_store.register(req, body.password)
    except Exception as e:
        raise HTTPException(400, str(e))
    token = user_store.create_token(profile.user_id)
    return {"token": token, "profile": profile.model_dump()}


@router.post("/auth/login")
def login(body: LoginRequest):
    profile = user_store.login(body.email, body.password)
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
