"""Exact weight-space robustness of a ranking.

Every score is linear in the objective weights: S_i(w) = sum_d w_d * a_id, where a_id is the confidence-adjusted value of
objective d for candidate i. The winner therefore holds against a rival j unless weight mass is moved toward objectives where j
is ahead. ``weight_margin`` returns the SMALLEST total-variation shift (1/2 * |dw|_1, so 0.10 means "10% of the total weight")
that makes j tie the winner. It is exact for this linear problem (fractional-knapsack greedy), not a sampled estimate.
None means no re-weighting can make the rival catch up (the winner is ahead on every objective that carries weight).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

EPS = 1e-15


def weight_margin(top: Dict[str, float], rival: Dict[str, float], weights: Dict[str, float]) -> Optional[float]:
    dims = [d for d in weights if d in top and d in rival]
    delta = {d: top[d] - rival[d] for d in dims}
    gap = math.fsum(weights[d] * delta[d] for d in dims)
    if gap <= 0:
        return 0.0
    j = min(dims, key=lambda d: (delta[d], d))          # the objective where the rival is furthest ahead: weight is moved INTO it
    if delta[j] >= 0:
        return None
    need, moved = gap, 0.0
    # take weight from objectives where the winner leads the most (largest delta - delta_j gain per unit moved)
    for d in sorted((d for d in dims if d != j and delta[d] > delta[j] and weights[d] > 0), key=lambda d: (-(delta[d] - delta[j]), d)):
        per_unit = delta[d] - delta[j]
        take = min(weights[d], need / per_unit)
        moved += take
        need -= take * per_unit
        if need <= EPS:
            break
    return moved if need <= 1e-12 else None


def min_weight_margin(order: Sequence[Tuple[str, Dict[str, float]]], weights: Dict[str, float]) -> Tuple[Optional[float], Optional[str]]:
    """order[0] is the winner. Returns (smallest margin over all rivals, id of the rival that sets it)."""
    if len(order) < 2:
        return None, None
    best: Optional[float] = None
    who: Optional[str] = None
    top = order[0][1]
    for rid, vals in order[1:]:
        m = weight_margin(top, vals, weights)
        if m is not None and (best is None or m < best - EPS):
            best, who = m, rid
    return best, who
