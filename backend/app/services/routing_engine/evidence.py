"""Evidence model: what is known about a metric, how well, and whether it may influence ranking.

Tiers (higher = stronger):
  T3  measured, with methodology, date and sample information
  T2  documented by an identifiable source
  T1  estimate with a named process and rationale
  T1u unverified / unanchored estimate         -> displayed, NEVER ranked
  T0  unknown                                   -> displayed as unknown, NEVER ranked
A value is RANKABLE iff its effective tier >= T1. Staleness demotes one tier; evidence for a different model id or task scope is not applicable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

T0, T1U, T1, T2, T3 = 0, 1, 2, 3, 4
TIER_NAME = {T0: "unknown", T1U: "unverified_estimate", T1: "estimate", T2: "documented", T3: "measured"}
RANKABLE_MIN = T1


@dataclass(frozen=True)
class EvidenceRecord:
    """Optional application-level evidence that overrides the registry's bare values (no database migration needed)."""
    metric: str
    value: float
    unit: str
    source: str
    tier: int
    model_id: str                      # evidence applies only to exactly this model id (ids carry the version)
    date: Optional[str] = None
    scope: str = "all"                 # task scope ("all" or a task type); a record for another task does not apply
    method: Optional[str] = None
    sample_size: Optional[int] = None
    plan: Optional[str] = None
    rationale: Optional[str] = None
    uncertainty: Optional[tuple] = None   # (low, high) only when the source itself supplies it


@dataclass
class Cell:
    """One (candidate, objective) input to the decision, with its evidence."""
    dimension: str
    value: Optional[float]             # utility in [0,1] USED IN RANKING, or None
    tier: int = T0
    display_value: Optional[float] = None   # value shown to the user when it is not rankable (e.g. an unverified estimate)
    unit: str = ""
    source: Optional[str] = None
    date: Optional[str] = None
    freshness: str = "undated"         # fresh | stale | undated | n/a
    note: str = ""
    sample_size: Optional[int] = None

    @property
    def rankable(self) -> bool:
        return self.value is not None and self.tier >= RANKABLE_MIN


def parse_date(raw: Any) -> Optional[date]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def freshness(raw_date: Any, max_age_days: int, today: Optional[date] = None) -> str:
    d = parse_date(raw_date)
    if d is None:
        return "undated"
    today = today or datetime.now(timezone.utc).date()
    return "stale" if (today - d).days > max_age_days else "fresh"


def effective_tier(tier: int, fresh: str) -> int:
    """Stale evidence is demoted one tier (a previously documented value is now only an estimate); undated evidence keeps its tier but is flagged,
    except that 'measured' requires a date, so an undated measurement counts as documented."""
    if fresh == "stale":
        return max(T0, tier - 1)
    if fresh == "undated" and tier == T3:
        return T2
    return tier


def applies(record: EvidenceRecord, model_id: str, task_type: Optional[str]) -> bool:
    return record.model_id == model_id and record.scope in ("all", task_type or "")


def records_for(store: Dict[str, List[EvidenceRecord]], model_id: str, task_type: Optional[str], metric: str) -> List[EvidenceRecord]:
    return [r for r in store.get(model_id, []) if r.metric == metric and applies(r, model_id, task_type)]
