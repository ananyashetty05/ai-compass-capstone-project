"""Fixed-anchor, candidate-independent normalization. Every function maps a raw value to a utility in [0, 1] where HIGHER IS ALWAYS BETTER,
or to None when the raw value is not a valid measurement (NaN, infinite, negative). Nothing here looks at other candidates."""
from __future__ import annotations

import math
from typing import Optional, Tuple

from app.services.routing_engine.policy import POLICY, ErPcrPolicy


def _log_utility(x: float, best: float, worst: float) -> float:
    lx, lb, lw = math.log10(x), math.log10(best), math.log10(worst)
    return max(0.0, min(1.0, 1.0 - (lx - lb) / (lw - lb)))


def cost_utility(usd_per_request: Optional[float], policy: ErPcrPolicy = POLICY) -> Optional[float]:
    """Lower cost -> higher utility. 0 (free) -> 1. Saturates at the anchors."""
    if usd_per_request is None or not math.isfinite(usd_per_request) or usd_per_request < 0:
        return None
    if usd_per_request == 0:
        return 1.0
    return round(_log_utility(usd_per_request, *policy.cost_usd_per_request), 6)


def latency_utility(seconds: Optional[float], policy: ErPcrPolicy = POLICY) -> Optional[float]:
    """Lower latency -> higher utility. Saturates at the anchors."""
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return None
    return round(_log_utility(seconds, *policy.latency_seconds), 6)


def unit_interval(x: Optional[float]) -> Optional[float]:
    """For values that are already on a documented 0-1 scale where higher is better (reliability success rate, fit)."""
    if x is None or not math.isfinite(x) or x < 0.0 or x > 1.0:
        return None
    return float(x)


def risk_suitability(exposure: Optional[float]) -> Optional[float]:
    """Exposure (0 = none, 1 = maximal) -> suitability = 1 - exposure."""
    e = unit_interval(exposure)
    return None if e is None else round(1.0 - e, 6)
