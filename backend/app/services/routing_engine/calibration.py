"""Calibration metrics for confidence values, computed only from labelled outcomes.

Nothing in the routing engine is calibrated by default: its confidence figures are heuristic estimates. This module is
the instrument for *validating* them once labelled outcomes exist (predicted confidence vs whether the outcome was right).
"""
from typing import Dict, List, Sequence, Tuple

MIN_OUTCOMES_FOR_VALIDATION = 200      # below this a reliability diagram is dominated by sampling noise
BINS = 10


def brier_score(confidences: Sequence[float], outcomes: Sequence[int]) -> float:
    _check(confidences, outcomes)
    return sum((c - o) ** 2 for c, o in zip(confidences, outcomes)) / len(confidences)


def reliability_bins(confidences: Sequence[float], outcomes: Sequence[int], bins: int = BINS) -> List[Dict[str, float]]:
    _check(confidences, outcomes)
    out: List[Dict[str, float]] = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if not idx:
            continue
        out.append({"lo": lo, "hi": hi, "n": len(idx), "mean_confidence": sum(confidences[i] for i in idx) / len(idx),
                    "observed_accuracy": sum(outcomes[i] for i in idx) / len(idx)})
    return out


def expected_calibration_error(confidences: Sequence[float], outcomes: Sequence[int], bins: int = BINS) -> float:
    n = len(confidences)
    return sum(b["n"] / n * abs(b["mean_confidence"] - b["observed_accuracy"]) for b in reliability_bins(confidences, outcomes, bins))


def status(n_labelled: int) -> Dict[str, object]:
    ok = n_labelled >= MIN_OUTCOMES_FOR_VALIDATION
    return {"validated": False, "labelled_outcomes": n_labelled, "minimum_for_validation": MIN_OUTCOMES_FOR_VALIDATION, "can_validate": ok,
            "statement": ("Confidence values are heuristic estimates and have not been calibrated against labelled outcomes."
                          if not ok else "Enough labelled outcomes exist to compute Brier score and expected calibration error; compute them before calling these probabilities.")}


def _check(c: Sequence[float], o: Sequence[int]) -> None:
    if len(c) != len(o) or not c:
        raise ValueError("confidences and outcomes must be non-empty and the same length")
    if any(not 0.0 <= x <= 1.0 for x in c) or any(y not in (0, 1) for y in o):
        raise ValueError("confidences must be in [0,1] and outcomes 0/1")
