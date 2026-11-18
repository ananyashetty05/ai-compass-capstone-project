"""Optional persistence for routing decisions, execution attempts and derived performance statistics.

Backed by the tables in ``migrations/20261119_route_query_engine.sql`` (NOT applied automatically).
Every function degrades safely when the tables or the database are unavailable: routing never fails
because logging does. Prompt text and secrets are never stored; only a short summary for non-sensitive queries.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.services.routing_engine.observed import ObservedStats, median

logger = get_logger(__name__)
_AVAILABLE: Optional[bool] = None


def _conn():
    from app.services.feedback_store import _conn as conn
    return conn()


def table_available(force: bool = False) -> bool:
    global _AVAILABLE
    if _AVAILABLE is not None and not force:
        return _AVAILABLE
    try:
        with _conn() as c:
            row = c.execute("SELECT to_regclass('public.routing_decision_log') AS t, to_regclass('public.routing_execution_log') AS e").fetchone()
        _AVAILABLE = bool(row and row["t"] and row["e"])
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


def summarize_query(query: str, sensitivity: str) -> str:
    if sensitivity in {"moderate", "high"}:
        return "[withheld: sensitive content]"
    one = " ".join(query.split())
    return one[:80] + ("…" if len(one) > 80 else "")


def record(routing_id: str, user_id: str, result: Any) -> bool:
    """Persist a compact record of a PipelineResult. Returns False when storage is unavailable."""
    if not table_available():
        return False
    try:
        sel = result.selection
        by_id = {c.model_id: c for c in result.candidates}
        final_id = result.execution.final_model_id or sel.selected_model_id
        final = by_id.get(final_id)
        compact = [{"model_id": c.model_id, "rank": c.rank, "utility": c.utility, "robust_score": c.robust_score, "utilities": c.utilities, "missing": c.missing_dimensions} for c in result.candidates]
        with _conn() as c:
            c.execute(
                """INSERT INTO routing_decision_log
                   (routing_id, user_id, created_at, engine_version, scoring_version, mode, primary_intent, complexity_score, sensitivity, optimization_mode,
                    selected_model_id, selected_model_name, final_model_id, final_model_name, candidate_count, excluded_count, weights, scores,
                    explanation_summary, execution_status, evaluation_status, routing_latency_ms, total_latency_ms, total_cost_usd, escalated, query_summary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (routing_id) DO NOTHING""",
                (routing_id, user_id, datetime.now(timezone.utc), result.version, result.scoring_version, result.mode, result.profile.primary_intent,
                 result.profile.complexity.score, result.profile.risk.sensitivity, result.optimization.mode, sel.selected_model_id,
                 by_id[sel.selected_model_id].model_name if sel.selected_model_id in by_id else None, final_id, final.model_name if final else None,
                 len(result.candidates), len(result.exclusions), json.dumps(result.preferences.weights), json.dumps(compact), result.explanation.summary,
                 result.execution.status, result.evaluation.status, result.routing_latency_ms, result.execution.total_latency_ms, result.execution.total_cost_usd,
                 result.execution.escalated, summarize_query(result.profile.original_query, result.profile.risk.sensitivity)))
            for a in result.execution.attempts:
                if a.outcome in {"success", "error"}:
                    c.execute(
                        """INSERT INTO routing_execution_log (routing_id, user_id, model_id, provider, outcome, error_kind, latency_ms, input_tokens, output_tokens, cost_usd, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (routing_id, user_id, a.model_id, a.provider, a.outcome, a.error_kind, a.latency_ms, a.input_tokens, a.output_tokens, a.cost_usd, datetime.now(timezone.utc)))
        return True
    except Exception:
        logger.exception("Could not persist routing decision log")
        return False


def observed_stats(model_ids: List[str], window_days: int = 30) -> Dict[str, ObservedStats]:
    if not model_ids or not table_available():
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    with _conn() as c:
        rows = c.execute("SELECT model_id, outcome, latency_ms FROM routing_execution_log WHERE model_id = ANY(%s) AND created_at >= %s", (list(model_ids), since)).fetchall()
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r["model_id"], []).append(r)
    out: Dict[str, ObservedStats] = {}
    for mid, items in buckets.items():
        ok = [i for i in items if i["outcome"] == "success"]
        lat = [i["latency_ms"] / 1000.0 for i in ok if i["latency_ms"] is not None]
        out[mid] = ObservedStats(model_id=mid, samples=len(items), successes=len(ok), latency_p50_seconds=median(lat), window_days=window_days)
    return out


def history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM routing_decision_log WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit)).fetchall()
    return [{
        "id": r["routing_id"], "timestamp": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        "query_summary": r["query_summary"] or "", "selected_model_id": r["selected_model_id"] or "", "selected_model_name": r["selected_model_name"] or "",
        "final_model_id": r["final_model_id"] or "", "final_model_name": r["final_model_name"] or "", "routing_latency_ms": r["routing_latency_ms"],
        "total_latency_ms": r["total_latency_ms"], "estimated_cost": r["total_cost_usd"], "escalated": bool(r["escalated"]),
        "mode": r["mode"], "execution_status": r["execution_status"], "scoring_version": r["scoring_version"]} for r in rows]


def get_decision(user_id: str, routing_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        r = c.execute("SELECT * FROM routing_decision_log WHERE routing_id = %s AND user_id = %s", (routing_id, user_id)).fetchone()
    if not r:
        return None
    r = dict(r)
    r["created_at"] = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
    for k in ("weights", "scores"):
        if isinstance(r.get(k), str):
            r[k] = json.loads(r[k])
    return r
