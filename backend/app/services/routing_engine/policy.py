"""ER-PCR policy: every tunable number in the decision engine lives here, with its meaning.

These are POLICY parameters (documented design choices), not statistics estimated from data. None of them is described to the user as a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

OBJECTIVES: Tuple[str, ...] = ("quality", "cost", "latency", "reliability", "risk")
FIT = "preference_alignment"                       # task fit: the registry/API name of the fit objective
ALL_OBJECTIVES: Tuple[str, ...] = (FIT, *OBJECTIVES)


@dataclass(frozen=True)
class ErPcrPolicy:
    # Weight of documented task fit when the user has also prioritised other objectives. With no stated priority, fit alone orders candidates.
    fit_share: float = 0.55
    # Fixed normalization anchors (candidate-independent). Utility 1 at/below the best anchor, 0 at/above the worst, log-linear between, saturating outside.
    cost_usd_per_request: Tuple[float, float] = (1e-5, 1e-1)      # best, worst
    latency_seconds: Tuple[float, float] = (0.2, 60.0)            # best, worst
    # Freshness windows in days, per kind of evidence (pricing changes fastest; capability and privacy terms change slower).
    freshness_days: Tuple[Tuple[str, int], ...] = (("pricing", 90), ("benchmark", 180), ("telemetry", 30), ("capability", 365), ("privacy", 365), ("default", 365))
    # A winner counts as robust to re-weighting if it survives this share of the total weight moved in the least favourable direction.
    safe_weight_shift: float = 0.10
    # Score differences below this (display only) are described as "almost identical"; ordering is always exact.
    near_tie_margin: float = 0.005
    score_decimals: int = 12

    def freshness_for(self, kind: str) -> int:
        d = dict(self.freshness_days)
        return d.get(kind, d["default"])


POLICY = ErPcrPolicy()


def validate_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Non-negative, finite, sums to 1. Raises ValueError otherwise (never silently repairs invalid input)."""
    import math
    if not weights:
        raise ValueError("weights must not be empty")
    for k, v in weights.items():
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(f"weight {k!r} must be a finite number >= 0")
    s = math.fsum(weights.values())
    if s <= 0:
        raise ValueError("weights must not all be zero")
    return {k: v / s for k, v in weights.items()}
