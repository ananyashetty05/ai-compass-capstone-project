"""Observed performance statistics (latency, success rate) with explicit sample counts.

``ObservedStats`` is a plain value object so scoring is a pure function of its inputs.
``load_observed`` reads the execution log when the (optional) migration has been applied;
otherwise it returns an empty mapping and routing falls back to registry metadata, labelled as such.
"""
import math
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel

MIN_SAMPLES = 5


class ObservedStats(BaseModel):
    model_id: str
    samples: int
    successes: int
    latency_p50_seconds: Optional[float] = None
    window_days: int = 30

    @property
    def success_lower_bound(self) -> Optional[float]:
        return wilson_lower_bound(self.successes, self.samples) if self.samples >= MIN_SAMPLES else None


def wilson_lower_bound(successes: int, n: int, z: float = 1.645) -> float:
    """One-sided 95% Wilson lower bound; a single lucky request cannot yield a high estimate."""
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def median(values: Iterable[float]) -> Optional[float]:
    xs = sorted(values)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def load_observed(model_ids: List[str], window_days: int = 30) -> Dict[str, ObservedStats]:
    try:
        from app.services import routing_log_store
        return routing_log_store.observed_stats(model_ids, window_days)
    except Exception:
        return {}
