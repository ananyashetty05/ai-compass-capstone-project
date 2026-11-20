"""Decision explanation generated only from structured decision data.

Each sentence is rendered from a fact record that is returned alongside the text
(``DecisionExplanation.facts``), so the narrative can be audited against the numbers.
"""
from typing import Any, Dict, List

from app.services.routing_engine import scoring as scoring_mod
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
    pw = top.score_weights or {}
    contribs = sorted(((d, top.contributions[d]) for d in DIMENSIONS if pw.get(d, 0) > 0), key=lambda kv: -kv[1])
    influential = [{"objective": LABEL[d], "weight": round(pw[d], 3), "utility": top.utilities[d], "contribution": round(c, 4)} for d, c in contribs[:3]]
    facts.append({"type": "selected", "model_id": top.model_id, "robust_score": top.robust_score, "utility": top.utility, "rank": 1, "candidates": len(rows)})
    scored = sum(1 for r in rows if scoring_mod.is_scored(r))
    pool = (f"{scored} scored candidate{'s' if scored != 1 else ''} ({len(rows) - scored} more are in the pool but have no documented or measured evidence "
            f"for any objective, so they cannot be compared and rank below every scored model)") if scored != len(rows) else f"{len(rows)} eligible candidate{'s' if len(rows) != 1 else ''}"
    facts.append({"type": "pool", "eligible": len(rows), "scored": scored, "unscored": len(rows) - scored})
    aud = profile.audience
    if aud.category == "developer_api":
        facts.append({"type": "category", "category": "developer_api", "signals": list(aud.signals)})
        why.append("Your request reads as building or integrating AI into a project, so Developer & API models (provider APIs, hosted inference, aggregators and model hubs) were considered. "
                   "Whether a model can be run from AI Compass is shown separately and did not affect the ranking.")
    else:
        facts.append({"type": "category", "category": "conversational", "ambiguous": aud.ambiguous})
        why.append("Your request reads as asking for an AI assistant, so only Conversational AI models were considered; Developer & API offerings were not mixed in."
                   + (" The request could also mean finding a model to build with: " + (aud.clarifying_question or "") if aud.ambiguous else ""))
    why.append(f"{top.model_name} ranked first of {pool} with an evidence-credited score of {top.robust_score:.3f}. "
               f"The score counts only evidence that may rank candidates: {', '.join(LABEL[d] for d in pw) or 'nothing'}.")
    if sel.decision_reason:
        why.append(f"Decision status: {sel.decision_status.replace('_', ' ')}. {sel.decision_reason}")
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
        used = d in pw
        unavailable.append(f"{LABEL[d]} data is unavailable for {top.model_name}; " + ("it earned no credit for it and the gap is reported." if used else "it is not used to rank."))
    groups: Dict[str, List[str]] = {"measured": [], "documented": [], "estimate": [], "unverified_estimate": [], "unknown": [], "stale": []}
    for d in DIMENSIONS:
        e = top.evidence[d]
        groups.setdefault(e.tier, []).append(LABEL[d])
        if e.freshness == "stale":
            groups["stale"].append(LABEL[d])
    if groups["unverified_estimate"]:
        unavailable.append("Hand-set estimates are shown but never used to rank: " + ", ".join(groups["unverified_estimate"]) + ".")
    if groups["stale"]:
        unavailable.append("Evidence older than its freshness window was demoted one tier: " + ", ".join(groups["stale"]) + ".")
    facts.append({"type": "data_quality", "missing": top.missing_dimensions, "estimated": groups["unverified_estimate"], "evidence_by_tier": groups, "ranking_objectives": list(pw)})

    conf = f"{sel.confidence_level.capitalize()} decision-reliability index ({sel.confidence_value:.2f}); this is a heuristic index, not a probability of being correct."
    if sel.weight_stability is not None:
        conf += f" The winner survives {_pct(sel.weight_stability)} of a 10% re-weighting in the least favourable direction (weight stability)."
    if sel.score_margin is not None:
        conf += f" Margin over the runner-up: {sel.score_margin:.3f}."
    if sel.tie_break_applied:
        conf += f" A near-tie was resolved by {sel.tie_break_applied}."
    facts.append({"type": "confidence", "level": sel.confidence_level, "value": sel.confidence_value, "stability": sel.weight_stability, "margin": sel.score_margin})
    if prefs.adjustments:
        why.append("Weights were adjusted for this query: " + "; ".join(f"{LABEL[a.dimension]} ×{a.factor:g} ({a.reason.lower()})" for a in prefs.adjustments) + ".")
    n_hc = len(_constraints(prefs))
    hc = f"{n_hc} explicit hard constraint(s) were satisfied" if n_hc else "no explicit hard constraints were set"
    lead = {"recommended": "recommends", "qualified": "tentatively recommends", "insufficient_evidence": "lists as best-supported (unverified)", "indistinguishable": "cannot separate its top candidates, and lists first",
            "needs_clarification": "provisionally lists"}.get(sel.decision_status, "recommends")
    summary = (f"AI Compass {lead} {top.model_name} ({top.provider}): {hc}"
               f"{'; ' + str(len(excluded)) + ' candidate(s) were excluded' if excluded else ''}, and it ranked first of {scored} scored model{'s' if scored != 1 else ''} under your {prefs.weight_source.replace('_', ' ')} objective weights.")
    return DecisionExplanation(summary=summary, why_selected=why, why_alternatives_ranked_lower=lower, hard_constraints_applied=_constraints(prefs),
                               influential_objectives=influential, unavailable_data=unavailable, tradeoffs=tradeoffs, confidence_statement=conf, facts=facts)


def _constraints(prefs: ResolvedPreferences) -> List[str]:
    out = []
    for c in prefs.hard_constraints:
        if c.kind == "execution_blocked":
            continue
        out.append(f"{c.kind.replace('_', ' ')}: {c.value}" if c.value is not True else c.kind.replace("_", " "))
    return out
