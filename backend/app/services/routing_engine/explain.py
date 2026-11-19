"""Decision explanation generated only from structured decision data.

Each sentence is rendered from a fact record that is returned alongside the text
(``DecisionExplanation.facts``), so the narrative can be audited against the numbers.
"""
from typing import Any, Dict, List

from app.services.routing_engine.preferences import DIMENSIONS
from app.services.routing_engine.types import CandidateScore, DecisionExplanation, ExclusionRecord, QueryProfileV2, ResolvedPreferences, Selection

LABEL = {"quality": "quality", "cost": "cost", "latency": "latency", "reliability": "reliability", "risk": "risk control", "preference_alignment": "task fit"}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def build(profile: QueryProfileV2, prefs: ResolvedPreferences, rows: List[CandidateScore], excluded: List[ExclusionRecord], sel: Selection) -> DecisionExplanation:
    facts: List[Dict[str, Any]] = []
    if not rows or not sel.selected_model_id:
        by: Dict[str, int] = {}
        for e in excluded:
            by[e.code] = by.get(e.code, 0) + 1
        facts.append({"type": "no_candidates", "exclusions_by_code": by})
        return DecisionExplanation(summary="No model satisfied every hard constraint, so none was selected.", hard_constraints_applied=_constraints(prefs),
                                   unavailable_data=[], confidence_statement="No decision was made.", facts=facts,
                                   why_alternatives_ranked_lower=[{"model_id": e.model_id, "reason": e.reason} for e in excluded[:10]])
    top = rows[0]
    why: List[str] = []
    contribs = sorted(((d, top.contributions[d]) for d in DIMENSIONS if prefs.weights[d] > 0), key=lambda kv: -kv[1])
    influential = [{"objective": LABEL[d], "weight": round(prefs.weights[d], 3), "utility": top.utilities[d], "contribution": round(c, 4)} for d, c in contribs[:3]]
    facts.append({"type": "selected", "model_id": top.model_id, "robust_score": top.robust_score, "utility": top.utility, "rank": 1, "candidates": len(rows)})
    why.append(f"{top.model_name} ranked first of {len(rows)} eligible candidate{'s' if len(rows) != 1 else ''} with a robust score of {top.robust_score:.3f} (utility {top.utility:.3f}).")
    if influential:
        i0 = influential[0]
        u = i0["utility"]
        why.append(f"The largest contribution came from {i0['objective']} (weight {_pct(i0['weight'])}, utility {u:.2f})." if u is not None
                   else f"The largest contribution came from {i0['objective']} (weight {_pct(i0['weight'])}).")
        facts.append({"type": "top_contribution", **i0})
    why.append(f"Its task fit for a {profile.primary_intent.replace('_', ' ')} request is {top.task_fit:.2f}.")
    if profile.domain != "general":
        facts.append({"type": "domain", "domain": profile.domain, "confidence": profile.domain_confidence})

    lower: List[Dict[str, Any]] = []
    tradeoffs: List[str] = []
    for alt in rows[1:4]:
        diffs = {d: (alt.contributions[d] - top.contributions[d]) for d in DIMENSIONS}
        worse = sorted(((d, v) for d, v in diffs.items() if v < 0), key=lambda kv: kv[1])[:2]
        better = sorted(((d, v) for d, v in diffs.items() if v > 0), key=lambda kv: -kv[1])[:1]
        reason = f"Robust score {alt.robust_score:.3f} vs {top.robust_score:.3f}"
        if worse:
            reason += "; weaker on " + ", ".join(LABEL[d] for d, _ in worse)
        if alt.dominated_by and top.model_id in alt.dominated_by:
            reason += "; Pareto-dominated by the selected model"
        lower.append({"model_id": alt.model_id, "model_name": alt.model_name, "robust_score": alt.robust_score, "gap": round(top.robust_score - alt.robust_score, 5), "reason": reason})
        facts.append({"type": "alternative", "model_id": alt.model_id, "gap": round(top.robust_score - alt.robust_score, 5)})
        for d, v in better:
            ua, ut = alt.utilities.get(d), top.utilities.get(d)
            if ua is not None and ut is not None and ua - ut >= 0.1:
                tradeoffs.append(f"{alt.model_name} scores higher on {LABEL[d]} ({ua:.2f} vs {ut:.2f}) but loses overall under your weights.")
                facts.append({"type": "tradeoff", "model_id": alt.model_id, "objective": d, "alt": ua, "selected": ut})

    unavailable: List[str] = []
    for d in top.missing_dimensions:
        unavailable.append(f"{LABEL[d]} data is unavailable for {top.model_name}; it was scored as worst-case (0), not average.")
    estimated = [LABEL[d] for d in ("quality", "cost", "latency", "reliability", "risk") if not top.evidence[d].missing and (top.evidence[d].provenance == "estimated" or "registry estimate" in top.evidence[d].unit)]
    if estimated:
        unavailable.append("These values are registry estimates, not measurements: " + ", ".join(estimated) + ".")
    facts.append({"type": "data_quality", "missing": top.missing_dimensions, "estimated": estimated})

    conf = f"{sel.confidence_level.capitalize()} confidence ({sel.confidence_value:.2f})."
    if sel.weight_stability is not None:
        conf += f" The winner stayed first in {_pct(sel.weight_stability)} of ±20% weight perturbations."
    if sel.score_margin is not None:
        conf += f" Margin over the runner-up: {sel.score_margin:.3f}."
    if sel.tie_break_applied:
        conf += f" A near-tie was resolved by {sel.tie_break_applied}."
    facts.append({"type": "confidence", "level": sel.confidence_level, "value": sel.confidence_value, "stability": sel.weight_stability, "margin": sel.score_margin})
    if prefs.adjustments:
        why.append("Weights were adjusted for this query: " + "; ".join(f"{LABEL[a.dimension]} ×{a.factor:g} ({a.reason.lower()})" for a in prefs.adjustments) + ".")
    n_hc = len(_constraints(prefs))
    hc = f"{n_hc} explicit hard constraint(s) were satisfied" if n_hc else "no explicit hard constraints were set"
    summary = (f"AI Compass recommends {top.model_name} ({top.provider}): {hc}"
               f"{'; ' + str(len(excluded)) + ' candidate(s) were excluded' if excluded else ''}, and it ranked first under your {prefs.weight_source.replace('_', ' ')} objective weights.")
    return DecisionExplanation(summary=summary, why_selected=why, why_alternatives_ranked_lower=lower, hard_constraints_applied=_constraints(prefs),
                               influential_objectives=influential, unavailable_data=unavailable, tradeoffs=tradeoffs, confidence_statement=conf, facts=facts)


def _constraints(prefs: ResolvedPreferences) -> List[str]:
    out = []
    for c in prefs.hard_constraints:
        if c.kind == "execution_blocked":
            continue
        out.append(f"{c.kind.replace('_', ' ')}: {c.value}" if c.value is not True else c.kind.replace("_", " "))
    return out
