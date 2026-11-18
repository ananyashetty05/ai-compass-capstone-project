
"""Feedback persistence and adaptive satisfaction learning."""
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.feedback import (
    FeedbackSubmission,
    FeedbackRecord,
    ModelSatisfaction,
    LearningState,
)

logger = get_logger(__name__)


class InvalidFeedbackError(ValueError):
    """Feedback does not correspond to an authenticated routing decision."""

PRIOR_MEAN = 3.0
PRIOR_WEIGHT = 2.0
MIN_SAMPLES_FOR_INFLUENCE = 3
CONFIDENCE_SATURATION = 20
MAX_LEARNING_BONUS = 0.12


def _conn():
    if psycopg is None:
        raise RuntimeError("PostgreSQL support is unavailable; install psycopg[binary].")
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    return psycopg.connect(
        settings.DATABASE_URL,
        row_factory=dict_row,
    )

def init_feedback_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                routing_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                query_summary TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'general',
                domain TEXT NOT NULL DEFAULT 'general',
                rating INTEGER NOT NULL,
                thumbs TEXT,
                reasons TEXT NOT NULL DEFAULT '[]',
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS model_satisfaction (
                user_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                sum_ratings REAL NOT NULL DEFAULT 0,
                sample_count INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (user_id, model_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS routing_decisions (
                routing_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                selected_model_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
    logger.info("PostgreSQL feedback tables initialised")


# ── Submission ────────────────────────────────────────────────────────────────

def record_routing_decision(routing_id: str, user_id: str, selected_model_id: str) -> None:
    """Persist the minimal ownership evidence needed to validate feedback."""
    with _conn() as c:
        c.execute(
            """INSERT INTO routing_decisions (routing_id, user_id, selected_model_id, created_at)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (routing_id) DO NOTHING""",
            (routing_id, user_id, selected_model_id, datetime.now(timezone.utc).isoformat()),
        )

def submit_feedback(user_id: str, sub: FeedbackSubmission) -> FeedbackRecord:
    fid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with _conn() as c:
        decision = c.execute(
            """SELECT selected_model_id FROM routing_decisions
               WHERE routing_id = %s AND user_id = %s""",
            (sub.routing_id, user_id),
        ).fetchone()
        if not decision:
            raise InvalidFeedbackError("Feedback must reference one of your recorded routing decisions.")
        if decision["selected_model_id"] != sub.model_id:
            raise InvalidFeedbackError("Feedback model does not match the recorded routing decision.")
        c.execute(
            """
            INSERT INTO feedback
            (feedback_id, user_id, routing_id, model_id, model_name,
             query_summary, task_type, domain, rating, thumbs, reasons,
             comment, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fid, user_id, sub.routing_id, sub.model_id, sub.model_name,
                sub.query_summary, sub.task_type, sub.domain, sub.rating,
                sub.thumbs, json.dumps(sub.reasons), sub.comment, now,
            ),
        )

        c.execute(
            """
            INSERT INTO model_satisfaction
                (user_id, model_id, sum_ratings, sample_count, last_updated)
            VALUES (%s, %s, %s, 1, %s)
            ON CONFLICT(user_id, model_id) DO UPDATE SET
                sum_ratings = model_satisfaction.sum_ratings + EXCLUDED.sum_ratings,
                sample_count = model_satisfaction.sample_count + 1,
                last_updated = EXCLUDED.last_updated
            """,
            (user_id, sub.model_id, float(sub.rating), now),
        )

    logger.info(
        f"Feedback {fid}: user={user_id} model={sub.model_id} rating={sub.rating}"
    )
    return FeedbackRecord(
        feedback_id=fid,
        user_id=user_id,
        created_at=now,
        **sub.model_dump(),
    )


# ── Retrieval ────────────────────────────────────────────────────────────────

def get_user_feedback(user_id: str, limit: int = 50) -> List[FeedbackRecord]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT * FROM feedback
            WHERE user_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()

    return [_row_to_record(r) for r in rows]


def _row_to_record(row) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=row["feedback_id"],
        user_id=row["user_id"],
        routing_id=row["routing_id"],
        model_id=row["model_id"],
        model_name=row["model_name"],
        query_summary=row["query_summary"],
        task_type=row["task_type"],
        domain=row["domain"],
        rating=row["rating"],
        thumbs=row["thumbs"],
        reasons=json.loads(row["reasons"]),
        comment=row["comment"],
        created_at=row["created_at"],
    )


# ── Learning ────────────────────────────────────────────────────────────────

def get_satisfaction_estimates(user_id: str) -> Dict[str, float]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT model_id, sum_ratings, sample_count
            FROM model_satisfaction WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()

    total_samples = sum(r["sample_count"] for r in rows)
    if total_samples < MIN_SAMPLES_FOR_INFLUENCE:
        return {}

    estimates: Dict[str, float] = {}
    for row in rows:
        n = row["sample_count"]
        if n < MIN_SAMPLES_FOR_INFLUENCE:
            continue
        posterior = (
            PRIOR_WEIGHT * PRIOR_MEAN + row["sum_ratings"]
        ) / (PRIOR_WEIGHT + n)
        estimates[row["model_id"]] = (posterior - 1.0) / 4.0

    return estimates


def get_learning_state(user_id: str) -> LearningState:
    with _conn() as c:
        fb_count = c.execute(
            "SELECT COUNT(*) AS n FROM feedback WHERE user_id = %s",
            (user_id,),
        ).fetchone()["n"]

        sat_rows = c.execute(
            """
            SELECT ms.model_id, ms.sum_ratings, ms.sample_count, ms.last_updated
            FROM model_satisfaction ms WHERE ms.user_id = %s
            """,
            (user_id,),
        ).fetchall()

    estimates = []
    for row in sat_rows:
        n = row["sample_count"]
        posterior = (
            PRIOR_WEIGHT * PRIOR_MEAN + row["sum_ratings"]
        ) / (PRIOR_WEIGHT + n)
        confidence = min(1.0, n / CONFIDENCE_SATURATION)

        estimates.append(
            ModelSatisfaction(
                model_id=row["model_id"],
                model_name=row["model_id"],
                mean_rating=round(posterior, 2),
                sample_count=n,
                confidence=round(confidence, 3),
                last_updated=row["last_updated"],
            )
        )

    estimates.sort(key=lambda e: e.sample_count, reverse=True)
    cold_start = fb_count < MIN_SAMPLES_FOR_INFLUENCE

    return LearningState(
        total_feedback=fb_count,
        models_rated=len(sat_rows),
        satisfaction_estimates=estimates,
        learning_active=not cold_start,
        cold_start=cold_start,
    )


def get_learning_bonuses(user_id: str, model_ids: List[str]) -> Dict[str, float]:
    """Return all requested user-local bonuses with one connection/query.

    This preserves the cold-start and per-model sample thresholds while avoiding
    one aggregate lookup per eligible routing candidate.
    """
    wanted = set(model_ids)
    if not wanted:
        return {}
    with _conn() as c:
        rows = c.execute(
            """
            SELECT model_id, sum_ratings, sample_count,
                   SUM(sample_count) OVER () AS total_samples
            FROM model_satisfaction WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()
    if not rows or rows[0]["total_samples"] < MIN_SAMPLES_FOR_INFLUENCE:
        return {}
    bonuses: Dict[str, float] = {}
    for row in rows:
        if row["model_id"] not in wanted or row["sample_count"] < MIN_SAMPLES_FOR_INFLUENCE:
            continue
        posterior = (PRIOR_WEIGHT * PRIOR_MEAN + row["sum_ratings"]) / (PRIOR_WEIGHT + row["sample_count"])
        deviation = (posterior - 1.0) / 4.0 - 0.5
        confidence = min(1.0, row["sample_count"] / CONFIDENCE_SATURATION)
        bonuses[row["model_id"]] = round(deviation * 2 * MAX_LEARNING_BONUS * confidence, 4)
    return bonuses


def get_learning_bonus(user_id: str, model_id: str) -> float:
    """Compatibility wrapper for callers requesting one model."""
    return get_learning_bonuses(user_id, [model_id]).get(model_id, 0.0)
