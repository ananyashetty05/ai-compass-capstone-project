"""Separate, labelled confidence components. They are never averaged into one number: they measure different things."""
from typing import Any, Dict, List, Optional

from app.services.routing_engine import calibration
from app.services.routing_engine.types import ConfidenceComponent, ConfidenceReport, EvaluationOutcome, ExecutionOutcome, QueryProfileV2, Selection


def build(profile: QueryProfileV2, selection: Selection, access: Dict[str, Any], execution: ExecutionOutcome, evaluation: EvaluationOutcome,
          *, labelled_outcomes: int = 0) -> ConfidenceReport:
    comps: List[ConfidenceComponent] = []
    ic, dc = profile.confidence.get("intent"), profile.confidence.get("domain")
    comps.append(ConfidenceComponent(
        name="query_understanding", value=min(v for v in (ic, dc) if v is not None) if ic is not None and dc is not None else None, kind="heuristic_estimate",
        detail={"intent_confidence": ic, "domain_confidence": dc, "needs_clarification": profile.needs_clarification,
                "ambiguities": [a.kind for a in profile.ambiguities]},
        basis="Lexical margin between the strongest and next intent/domain evidence; the lower of the two is shown. Not a probability."))
    comps.append(ConfidenceComponent(
        name="model_suitability", value=selection.confidence_value if selection.selected_model_id else None, kind="heuristic_estimate",
        detail={"level": selection.confidence_level, "weight_stability": selection.weight_stability, "score_margin": selection.score_margin},
        basis="0.5 x evidence confidence of the selected model + 0.3 x ranking stability under +/-20% weight changes + 0.2 x score margin. Not a probability."))
    ready = access.get("execution_available") if access else None
    comps.append(ConfidenceComponent(
        name="execution_readiness", value=None if ready is None else (1.0 if ready else 0.0), kind="deterministic",
        detail={"status": access.get("status") if access else None, "next_step": access.get("next_step") if access else None},
        basis="Whether a compatible adapter and server credential exist for the selected model right now (1 = yes, 0 = no). A fact, not an estimate."))
    if execution.status == "not_requested":
        comps.append(ConfidenceComponent(name="response_acceptance", value=None, kind="not_applicable", detail={"reason": "No model was run (recommendation mode)."},
                                         basis="Only exists after execution."))
    else:
        comps.append(ConfidenceComponent(
            name="response_acceptance", value=None, kind="deterministic",
            detail={"accepted": evaluation.accepted, "execution_status": execution.status, "checks_not_run": [c.get("name") for c in evaluation.checks_not_run]},
            basis="Accept/reject comes from deterministic checks only (non-empty, not a refusal, requested format and length). It says nothing about factual correctness; "
                  "model self-reported confidence is never used."))
    return ConfidenceReport(components=comps, combined=None,
                            combined_note="No single combined confidence is reported: the components measure different things and none is calibrated.",
                            calibration=calibration.status(labelled_outcomes))
