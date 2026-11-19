"""Observed performance statistics (latency, success rate) with explicit sample counts.

``ObservedStats`` is a plain value object so scoring is a pure function of its inputs.
``load_observed`` reads the execution log when the (optional) migration has been applied;
otherwise it returns an empty mapping and routing falls back to registry metadata, labelled as such.
"""
import math
import threading
import time
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


OBSERVED_TTL_SECONDS = 30.0
STALE_SERVE_SECONDS = 600.0      # an expired entry this young is served immediately while a background refresh runs
_refreshing: set = set()
_cache: Dict[tuple, tuple] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def load_observed(model_ids: List[str], window_days: int = 30, ttl: float = OBSERVED_TTL_SECONDS) -> Dict[str, ObservedStats]:
    """Telemetry is aggregate and slow-moving, so it is cached for ``ttl`` seconds per (candidate set, window). A failed read is not cached.
    The decision fingerprint includes the observed values, so a routing change caused by new telemetry is visible."""
    key = (hash(frozenset(model_ids)), len(model_ids), window_days)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        if hit and now - hit[0] < STALE_SERVE_SECONDS and key not in _refreshing:
            _refreshing.add(key)
            ids = list(model_ids)
            threading.Thread(target=_refresh, args=(key, ids, window_days), name="observed-refresh", daemon=True).start()
            return hit[1]                       # stale-while-revalidate: telemetry is slow-moving, the request does not wait
        if hit and now - hit[0] < STALE_SERVE_SECONDS:
            return hit[1]
    value = _read(model_ids, window_days)
    if value is None:
        return {}
    with _lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (now, value)
    return value


def _read(model_ids: List[str], window_days: int):
    try:
        from app.services import routing_log_store
        return routing_log_store.observed_stats(model_ids, window_days)
    except Exception:
        return None                              # a failed read is never cached


def _refresh(key: tuple, model_ids: List[str], window_days: int) -> None:
    try:
        value = _read(model_ids, window_days)
        if value is not None:
            with _lock:
                _cache[key] = (time.monotonic(), value)
    finally:
        with _lock:
            _refreshing.discard(key)
