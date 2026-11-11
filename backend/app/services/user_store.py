"""
AI Compass - SQLite User Store with JWT auth.
Replaces the in-memory store with a real persistent database.
"""
import sqlite3
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.schemas.profile import (
    PersistentUserProfile, RoutingPreferences, AccessibilityPreferences,
    RegisterRequest, GROUP_DEFAULT_PREFERENCES
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
# PBKDF2-SHA256 is implemented by Passlib itself, supports long passphrases,
# and does not rely on an optional native hashing backend. bcrypt remains only
# for verifying accounts created by earlier versions.
pwd_ctx = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

DB = settings.DB_PATH


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                user_group TEXT NOT NULL,
                routing_preferences TEXT NOT NULL,
                accessibility_preferences TEXT NOT NULL,
                theme_preference TEXT DEFAULT 'system',
                preferences_customized INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.commit()
    logger.info("DB initialised")


def _row_to_profile(row) -> PersistentUserProfile:
    return PersistentUserProfile(
        user_id=row["user_id"],
        name=row["name"],
        email=row["email"],
        user_group=row["user_group"],
        routing_preferences=RoutingPreferences(**json.loads(row["routing_preferences"])),
        accessibility_preferences=AccessibilityPreferences(**json.loads(row["accessibility_preferences"])),
        theme_preference=row["theme_preference"],
        preferences_customized=bool(row["preferences_customized"]),
    )


def register(req: RegisterRequest, password: str) -> PersistentUserProfile:
    group = req.user_group.lower()
    if group not in GROUP_DEFAULT_PREFERENCES:
        raise ValueError(f"Invalid user_group: {group}")

    user_id = str(uuid.uuid4())
    prefs = req.routing_preferences or RoutingPreferences(**GROUP_DEFAULT_PREFERENCES[group])
    acc = req.accessibility_preferences or AccessibilityPreferences()
    customized = req.routing_preferences is not None

    with _conn() as c:
        c.execute(
            """INSERT INTO users
               (user_id, name, email, password_hash, user_group,
                routing_preferences, accessibility_preferences, theme_preference, preferences_customized)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                user_id, req.name, req.email,
                pwd_ctx.hash(password),
                group,
                json.dumps(prefs.model_dump()),
                json.dumps(acc.model_dump()),
                req.theme_preference,
                int(customized),
            )
        )
        c.commit()

    logger.info(f"Registered: {user_id} ({group})")
    return get_by_id(user_id)


def login(email: str, password: str) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not pwd_ctx.verify(password, row["password_hash"]):
        return None
    return _row_to_profile(row)


def get_by_id(user_id: str) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    return _row_to_profile(row) if row else None


def update_preferences(user_id: str, prefs: RoutingPreferences) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        c.execute(
            "UPDATE users SET routing_preferences=?, preferences_customized=1 WHERE user_id=?",
            (json.dumps(prefs.model_dump()), user_id)
        )
        c.commit()
    return get_by_id(user_id)


def update_profile_fields(user_id: str, name: str = None, theme: str = None,
                          accessibility: AccessibilityPreferences = None) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        if name:
            c.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
        if theme:
            c.execute("UPDATE users SET theme_preference=? WHERE user_id=?", (theme, user_id))
        if accessibility:
            c.execute("UPDATE users SET accessibility_preferences=? WHERE user_id=?",
                      (json.dumps(accessibility.model_dump()), user_id))
        c.commit()
    return get_by_id(user_id)


# ── JWT helpers ──────────────────────────────────────────────────────────────

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# Initialise DB on import
init_db()
