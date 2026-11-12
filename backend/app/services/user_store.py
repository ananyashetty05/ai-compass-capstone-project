
"""
AI Compass - PostgreSQL User Store with JWT auth.
"""
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from passlib.context import CryptContext
from jose import jwt, JWTError

from app.schemas.profile import (
    PersistentUserProfile, RoutingPreferences, AccessibilityPreferences,
    RegisterRequest, GROUP_DEFAULT_PREFERENCES
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

pwd_ctx = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto"
)


def _conn():
    return psycopg.connect(
        settings.DATABASE_URL,
        row_factory=dict_row
    )


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
    logger.info("PostgreSQL users table initialised")


def _row_to_profile(row) -> PersistentUserProfile:
    return PersistentUserProfile(
        user_id=row["user_id"],
        name=row["name"],
        email=row["email"],
        user_group=row["user_group"],
        routing_preferences=RoutingPreferences(
            **json.loads(row["routing_preferences"])
        ),
        accessibility_preferences=AccessibilityPreferences(
            **json.loads(row["accessibility_preferences"])
        ),
        theme_preference=row["theme_preference"],
        preferences_customized=bool(row["preferences_customized"]),
    )


def register(req: RegisterRequest, password: str) -> PersistentUserProfile:
    group = req.user_group.lower()
    if group not in GROUP_DEFAULT_PREFERENCES:
        raise ValueError(f"Invalid user_group: {group}")

    user_id = str(uuid.uuid4())
    prefs = req.routing_preferences or RoutingPreferences(
        **GROUP_DEFAULT_PREFERENCES[group]
    )
    acc = req.accessibility_preferences or AccessibilityPreferences()
    customized = req.routing_preferences is not None

    with _conn() as c:
        c.execute(
            """INSERT INTO users
               (user_id, name, email, password_hash, user_group,
                routing_preferences, accessibility_preferences,
                theme_preference, preferences_customized)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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

    logger.info(f"Registered: {user_id} ({group})")
    return get_by_id(user_id)


def login(email: str, password: str) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE email=%s", (email,)
        ).fetchone()

    if not row or not pwd_ctx.verify(password, row["password_hash"]):
        return None

    return _row_to_profile(row)


def get_by_id(user_id: str) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE user_id=%s", (user_id,)
        ).fetchone()

    return _row_to_profile(row) if row else None


def update_preferences(
    user_id: str, prefs: RoutingPreferences
) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        c.execute(
            """UPDATE users
               SET routing_preferences=%s, preferences_customized=1
               WHERE user_id=%s""",
            (json.dumps(prefs.model_dump()), user_id)
        )

    return get_by_id(user_id)


def update_profile_fields(
    user_id: str,
    name: str = None,
    theme: str = None,
    accessibility: AccessibilityPreferences = None
) -> Optional[PersistentUserProfile]:
    with _conn() as c:
        if name:
            c.execute(
                "UPDATE users SET name=%s WHERE user_id=%s",
                (name, user_id)
            )

        if theme:
            c.execute(
                "UPDATE users SET theme_preference=%s WHERE user_id=%s",
                (theme, user_id)
            )

        if accessibility:
            c.execute(
                """UPDATE users
                   SET accessibility_preferences=%s WHERE user_id=%s""",
                (json.dumps(accessibility.model_dump()), user_id)
            )

    return get_by_id(user_id)


# ── JWT helpers ──────────────────────────────────────────────────────────────

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload.get("sub")
    except JWTError:
        return None


# Initialise DB on import
init_db()
