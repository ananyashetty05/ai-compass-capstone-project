"""ER-PCR decision mathematics (pure functions, no I/O).

Objectives J = {fit, quality, cost, latency, reliability, risk}; every utility is in [0,1], HIGHER = BETTER.

Which objectives rank candidates (the "primary set" P):
    fit is always primary. A further objective d is primary iff the USER prioritised it: its explicit weight exceeds the system default, or an
    explicit adjustment raised it. Query-inferred multipliers and the old quality floor never enter the ranking (they were hand-set constants).
    Objectives outside P are shown with their evidence but do not rank candidates, so a candidate cannot win merely because more of its
    metadata happens to be filled in.

Weights over P (sum 1):
    P empty            : w_fit = 1
    P non-empty        : w_fit = f (policy fit_share); w_d = (1 - f) * e_d / sum_{k in P} e_k,   e_d = explicit weight of d

Score of candidate i (credit only for evidence that may rank; an unknown is neither zero nor perfect, it is simply not credited, and the
unknown share is reported):
    S_i   = sum_{d in P} w_d * u_id * 1[cell (i,d) rankable]
    U_i   = sum_{d in P} w_d * (u_id if rankable else 1)          # best case if every unknown primary objective were perfect (displayed only)
    gaps_i = {d in P : cell (i,d) not rankable}

Order (exact, deterministic): (-round(S_i,12), -round(feedback_i,12), not preferred_provider, known cost, editorial order, model id).
The ordering of two candidates depends only on those two candidates, so adding or removing any other candidate cannot change it.

Decision status (no tuned thresholds):
    no_eligible_candidates : M_q is empty
    needs_clarification    : the query is ambiguous in a way that changes the answer
    insufficient_evidence  : some objective in P is not rankable for the top candidate (the user's priority cannot be verified for it)
    indistinguishable      : the top candidates have exactly equal S and equal feedback; they are returned as a set
    qualified              : a strict leader exists but a rival overtakes it if <= safe_weight_shift of the weight moves (exact margin), or the
                             leader was separated only by the user's own feedback
    recommended            : strict leader, all of P evidenced for it, robust to the safe re-weighting
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.routing_engine.evidence import Cell
from app.services.routing_engine.policy import ALL_OBJECTIVES, FIT, OBJECTIVES, POLICY, ErPcrPolicy, validate_weights

EPS = 1e-9


def explicit_weights(base: Dict[str, float], adjustments: Sequence, defaults: Dict[str, float]) -> Tuple[Dict[str, float], List[str]]:
    """Weights the USER stated: base (saved/override/default) x explicit factors only, normalised. Returns (weights, prioritised objectives)."""
    e = {d: float(base.get(d, defaults[d])) for d in ALL_OBJECTIVES}
    for a in adjustments:
        if getattr(a, "origin", "explicit") == "explicit" and a.dimension in e and a.factor > 0:
            e[a.dimension] *= a.factor
    tot_e, tot_d = math.fsum(e.values()), math.fsum(defaults[d] for d in ALL_OBJECTIVES)
    # prioritised = the user's normalised share of d exceeds its default share (threshold-free: any increase over the default counts)
    prioritised = [d for d in OBJECTIVES if e[d] / tot_e > defaults[d] / tot_d + EPS]
    return validate_weights(e), prioritised


def primary_weights(explicit: Dict[str, float], prioritised: Sequence[str], policy: ErPcrPolicy = POLICY) -> Dict[str, float]:
    if not prioritised:
        return {FIT: 1.0}
    tot = math.fsum(explicit[d] for d in prioritised)
    if tot <= 0:
        return {FIT: 1.0}
    f = policy.fit_share
    return {FIT: f, **{d: (1.0 - f) * explicit[d] / tot for d in prioritised}}


def score(cells: Dict[str, Cell], weights: Dict[str, float]) -> Tuple[float, float, List[str]]:
    """(S, U, gaps): credited score, best-case score, primary objectives without rankable evidence."""
    s = u = 0.0
    gaps: List[str] = []
    for d, w in weights.items():
        c = cells.get(d)
        if c is not None and c.rankable:
            s += w * c.value  # type: ignore[operator]
            u += w * c.value  # type: ignore[operator]
        else:
            u += w
            gaps.append(d)
    return s, u, gaps


def order_key(s: float, feedback: float, preferred: bool, cost: Optional[float], editorial: int, model_id: str, policy: ErPcrPolicy = POLICY):
    return (-round(s, policy.score_decimals), -round(feedback, policy.score_decimals), not preferred, cost if cost is not None else float("inf"), editorial, model_id)


def status(*, n: int, tied_top: int, strict_leader: bool, gaps_top: Sequence[str], margin: Optional[float], feedback_decided: bool,
           needs_clarification: bool, policy: ErPcrPolicy = POLICY) -> Tuple[str, str]:
    """(decision_status, one-sentence reason). Pure function of already-computed facts."""
    if n == 0:
        return "no_eligible_candidates", "No candidate satisfied the mandatory requirements."
    if needs_clarification:
        return "needs_clarification", "The request is ambiguous in a way that changes the answer; clarify it before relying on this recommendation."
    if gaps_top:
        return "insufficient_evidence", ("The objectives you prioritised cannot be verified for the top candidate: " + ", ".join(gaps_top) +
                                        ". It is shown as the best-supported option, not as a verified winner.")
    if n > 1 and tied_top > 1:
        return "indistinguishable", f"{tied_top} candidates are equally suitable on the evidence that may rank them; they are returned as a set."
    if n > 1 and feedback_decided:
        return "qualified", "Candidates were equally suitable on the evidence; your own past feedback separated them."
    if n > 1 and margin is not None and margin < policy.safe_weight_shift:
        return "qualified", (f"The lead depends on how objectives are weighted: moving {margin:.1%} of the weight would let a rival win "
                             f"(a lead should survive {policy.safe_weight_shift:.0%}).")
    return "recommended", "A single candidate leads on all the evidence that may rank candidates, and the lead survives re-weighting."
