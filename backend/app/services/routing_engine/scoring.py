"""ER-PCR scoring and selection. Equations and policy: see ``decision.py`` and ``policy.py``.

Per candidate and objective an evidenced Cell is built (``cells.py``). Only rankable evidence (documented, measured, or an estimate with a named process)
may rank; hand-set editorial estimates are displayed but never ranked. Ranking objectives are task fit plus the objectives the USER prioritised.
The order is exact and deterministic; if candidates cannot be separated on the evidence, the result says so (decision_status) instead of inventing a winner.
"""
import math
from typing import Dict, List, Optional, Tuple

from app.schemas.model import ModelMetadata
from app.services.routing_engine import cells as cells_mod, decision, evidence as ev_mod
from app.services.routing_engine.filtering import estimate_request_cost
from app.services.routing_engine.observed import ObservedStats
from app.services.routing_engine.policy import ALL_OBJECTIVES, FIT, POLICY
from app.services.routing_engine.preferences import DEFAULT_WEIGHTS, DIMENSIONS
from app.services.routing_engine.robustness import min_weight_margin, weight_margin
from app.services.routing_engine.types import (
    CandidateScore, MetricEvidence, NormalizationDetails, QueryProfileV2, ResolvedPreferences, ScoringConfig, Selection,
)

_PARETO_DIMS = ("quality", "cost", "latency", "reliability", "risk")
FEEDBACK_CAP = 0.2


def _tags(model: ModelMetadata) -> set:
    return {t.lower() for t in [*model.capabilities, *model.supported_tasks]}


def task_fit(model: ModelMetadata, profile: QueryProfileV2) -> Optional[float]:
    # An explicitly requested specialised model type (e.g. embedding) that the model *is* fits exactly;
    # generic intent tags such as "qa" say nothing about embedding models.
    if model.model_type in profile.audience.required_model_types:
        return 1.0
    tags = _tags(model) - {"unknown"}
    if not tags:
        return None
    primary = 1.0 if tags & {t.lower() for t in profile.task_tags} else 0.0
    sec = profile.secondary_intents
    if not sec:
        return primary
    covered = sum(1 for i in sec if tags & {t.lower() for t in i.registry_tags}) / len(sec)
    return round(0.7 * primary + 0.3 * covered, 4)


# ── Approved-ecosystem scoring ───────────────────────────────────────────────────────────────────────────────────────────
# Every candidate here already serves the resolved category (filtering). The objective is *fit*: how well the product's
# documented strengths cover what the query asks for. No numeric quality/latency/reliability/risk exists for these
# products, so those objectives are excluded for every candidate instead of being filled with estimates.
ALIGNMENT_WEIGHTS = {"feature_fit": 0.5, "intent_fit": 0.3, "category_fit": 0.2}
INTENT_CATEGORIES = {"conversational", "coding", "api_models"}      # categories where the detected intent (qa, math, writing, ...) separates products
SECONDARY_ROLE_FIT = 0.85
_PRICING_UTILITY = {"completely_free": 1.0, "self_hosted_open_weight": 1.0, "free_tier_limited": 0.75, "pay_as_you_go": 0.5, "paid_subscription": 0.3}
MARGIN_FULL = 0.10


def is_ecosystem(models) -> bool:
    return bool(models) and all(getattr(m, "ecosystem_approved", False) for m in models)


MARGIN_FULL = 0.10


def is_ecosystem(models) -> bool:
    return bool(models) and all(getattr(m, "ecosystem_approved", False) for m in models)


SELECTION_CONFIDENCE_FORMULA = ("confidence = 0.35 x category_confidence + 0.35 x ranking_margin + 0.30 x feature_support; "
                                "capped at 0.45 when the request needs clarification and at 0.60 when it fits two categories. "
                                "All inputs come from the ranking; no model answer is involved.")


def ecosystem_confidence(top: CandidateScore, second: Optional[CandidateScore], profile: QueryProfileV2) -> Tuple[float, Dict[str, float], List[str]]:
    cat = profile.category
    category_conf = cat.confidence if cat else 0.0
    margin = (top.robust_score - second.robust_score) if second is not None else None
    margin_score = min(1.0, max(0.0, margin) / MARGIN_FULL) if margin is not None else 0.5
    features_requested = bool(cat and cat.features)
    feature_support = (top.feature_coverage if top.feature_coverage is not None else 0.5) if features_requested else 0.5
    value = 0.35 * category_conf + 0.35 * margin_score + 0.30 * feature_support
    notes: List[str] = []
    if profile.needs_clarification:
        value = min(value, 0.45)
        notes.append("capped at 0.45: the request needs clarification")
    elif cat and cat.ambiguous:
        value = min(value, 0.60)
        notes.append("capped at 0.60: the request fits two categories")
    comps = {"category_confidence": round(category_conf, 3), "ranking_margin": round(margin_score, 3), "feature_support": round(feature_support, 3),
             "score_margin": round(margin, 4) if margin is not None else 0.0}
    return round(value, 3), comps, notes



OBJECTIVES = ("quality", "cost", "latency", "reliability", "risk")
_TIER_CONF = {ev_mod.T3: 1.0, ev_mod.T2: 0.85, ev_mod.T1: 0.6, ev_mod.T1U: 0.0, ev_mod.T0: 0.0}
_TIER_LABEL = {ev_mod.T3: "measured", ev_mod.T2: "documented", ev_mod.T1: "estimate", ev_mod.T1U: "unverified_estimate", ev_mod.T0: "unknown"}
_SPEED_NAME = {"latency": "speed"}


def is_scored(row: CandidateScore) -> bool:
    """True when at least one objective has rankable evidence. A listed model with none of them is in the pool but cannot be compared."""
    if row.utilities.get(FIT) is not None:
        return True
    return any(e.tier in ("measured", "documented") and e.used_in_ranking is not None and row.utilities.get(d) is not None for d, e in row.evidence.items())


def _store(store):
    if store is not None:
        return store
    from app.data.evidence_records import RECORDS
    return RECORDS


def _ecosystem_fit(m: ModelMetadata, profile: QueryProfileV2) -> Tuple[ev_mod.Cell, Dict[str, float], str, List[str], List[str], Optional[float]]:
    from app.services.routing_engine import ecosystem
    cat = profile.category
    features = cat.features if cat else []
    use_intent = bool(cat and cat.category in INTENT_CATEGORIES)
    parts = {k: v for k, v in ALIGNMENT_WEIGHTS.items() if use_intent or k != "intent_fit"}
    tot = sum(parts.values())
    parts = {k: v / tot for k, v in parts.items()}
    cov, matched, unmet = ecosystem.feature_coverage(m, features)
    role = "primary" if cat is None or m.ecosystem_category == cat.category else "secondary"
    breakdown = {"feature_fit": cov, "category_fit": 1.0 if role == "primary" else SECONDARY_ROLE_FIT}
    if use_intent:
        intent = task_fit(m, profile)
        breakdown["intent_fit"] = intent if intent is not None else 0.0
    align = round(sum(parts[k] * breakdown[k] for k in parts), 4)
    note = ("matched " + (", ".join(matched) or "none") + ("; unmet " + ", ".join(unmet) if unmet else "")) if features else "no specific feature requested; category membership only"
    if cat and cat.unsatisfiable_features:
        note += "; not offered by any product in this category (not counted): " + ", ".join(cat.unsatisfiable_features)
    cell = ev_mod.Cell(FIT, align, ev_mod.T2, display_value=align, unit="0-1 documented-feature fit", source=m.provider_source or m.external_url, freshness="n/a", note=note)
    return cell, breakdown, role, matched, unmet, (cov if features else None)


def _live_fit(m: ModelMetadata, profile: QueryProfileV2) -> ev_mod.Cell:
    f = task_fit(m, profile)
    if f is None:
        return ev_mod.Cell(FIT, None, ev_mod.T0, note="The model declares no tasks or capabilities")
    documented = (m.metric_provenance or {}).get("capabilities") in cells_mod.DOCUMENTED
    return ev_mod.Cell(FIT, f, ev_mod.T2 if documented else ev_mod.T1, display_value=f, unit="0-1 task fit", source=m.provider_source or m.external_url, freshness="n/a",
                       note="declared capabilities and tasks matched to the request" + ("" if documented else " (registry-declared, not provider-published)"))


def _evidence(c: ev_mod.Cell, used: bool) -> MetricEvidence:
    return MetricEvidence(dimension=c.dimension, raw_value=c.display_value if c.display_value is not None else c.value, unit=c.unit, provenance="editorial_estimate" if c.tier == ev_mod.T1U else _TIER_LABEL[c.tier], confidence=_TIER_CONF[c.tier],
                          missing=c.tier == ev_mod.T0, note=c.note, tier=_TIER_LABEL[c.tier], used_in_ranking=used and c.rankable, freshness=c.freshness, source=c.source, date=c.date,
                          sample_size=c.sample_size)


def build_rows(models: List[ModelMetadata], profile: QueryProfileV2, prefs: ResolvedPreferences, *, observed: Optional[Dict[str, ObservedStats]] = None,
               learning: Optional[Dict[str, float]] = None, config: Optional[ScoringConfig] = None, order: Optional[Dict[str, int]] = None, evidence_store=None,
               today=None) -> Tuple[List[CandidateScore], NormalizationDetails]:
    cfg = config or ScoringConfig()
    observed, learning = observed or {}, learning or {}
    eco = is_ecosystem(models)
    explicit, prioritised = decision.explicit_weights(prefs.base_weights, prefs.adjustments, DEFAULT_WEIGHTS)
    pw = decision.primary_weights(explicit, prioritised, POLICY)
    store = _store(evidence_store)
    rows: List[CandidateScore] = []
    for m in models:
        usd = None if eco else estimate_request_cost(m, profile.tokens.input_tokens, profile.tokens.output_tokens)
        cells = cells_mod.objective_cells(m, profile, ecosystem=eco, observed=observed.get(m.model_id), request_cost_usd=usd, store=store, today=today)
        breakdown: Dict[str, float] = {}
        role, matched, unmet, cov = None, [], [], None
        if eco:
            cells[FIT], breakdown, role, matched, unmet, cov = _ecosystem_fit(m, profile)
        else:
            cells[FIT] = _live_fit(m, profile)
        S, U, gaps = decision.score(cells, pw)
        bonus = max(-FEEDBACK_CAP, min(FEEDBACK_CAP, learning.get(m.model_id, 0.0)))
        util = {d: (cells[d].value if cells[d].rankable else None) for d in DIMENSIONS}
        util = {d: (round(v, 4) if v is not None else None) for d, v in util.items()}
        ev = {d: _evidence(cells[d], d in pw) for d in DIMENSIONS}
        contrib = {d: round(pw[d] * cells[d].value, 5) if d in pw and cells[d].rankable else 0.0 for d in DIMENSIONS}
        sufficiency = math.fsum(w for d, w in pw.items() if cells[d].rankable)
        adjusted = {d: (cells[d].value if cells[d].rankable else 0.0) for d in pw}
        rows.append(CandidateScore(
            model_id=m.model_id, model_name=m.model_name, provider=m.provider, entry_type=m.entry_type, executable=(not eco) and m.entry_type == "inference_model" and m.adapter_compatible,
            utilities=util, contributions=contrib, evidence=ev, missing_dimensions=[d for d in DIMENSIONS if cells[d].tier == ev_mod.T0], confidence=round(sufficiency, 4),
            utility=round(S, 5), robust_score=round(S, 6), score_upper=round(U, 6), evidence_gaps=gaps, estimated_cost_usd=usd,
            learning_adjustment=round(bonus, 4), task_fit=round(cells[FIT].value or 0.0, 4), preferred_provider=m.provider.lower() in prefs.preferred_providers,
            metadata_status=m.metadata_status, score_weights=dict(pw), adjusted_values={d: round(v, 6) for d, v in adjusted.items()},
            ecosystem_category=m.ecosystem_category if eco else None, category_role=role, feature_coverage=cov, matched_features=matched, unmet_features=unmet,
            fit_breakdown={k: round(v, 4) for k, v in breakdown.items()}, external_url=m.external_url if eco else None, strengths=list(m.strengths or []) if eco else [],
            editorial_order=(order or {}).get(m.model_id, m.fallback_priority), pricing_category=m.pricing_category if eco else None, free_tier_available=m.free_tier_available if eco else None))
    notes = ["Ranking uses task fit plus the objectives you prioritised, each only where documented or measured evidence exists.",
             "Quality, speed, reliability and risk values that are hand-set estimates are displayed with their status but never used to rank.",
             "Credentials and API keys play no part in this comparison."]
    if prioritised:
        notes.append("Prioritised by you: " + ", ".join(_SPEED_NAME.get(d, d) for d in prioritised) + ".")
    else:
        notes.append("You stated no priority beyond task fit, so task fit alone ranks the candidates.")
    cost_used, lat_used = "cost" in pw, "latency" in pw
    norm = NormalizationDetails(cost_basis=("access_class" if eco else "fixed_anchor_log_usd_per_request") if cost_used else "not_used",
                                cost_method=("curated access class" if eco else "log scale, fixed anchors (candidate-independent)") if cost_used else "not used: you did not prioritise cost",
                                latency_basis="fixed_anchor_log_seconds" if lat_used else "not_used", uncertainty_penalty=0.0, missing_policy=cfg.missing_policy, notes=notes,
                                ranges={"cost_usd": {"best": POLICY.cost_usd_per_request[0], "worst": POLICY.cost_usd_per_request[1]}, "latency_s": {"best": POLICY.latency_seconds[0], "worst": POLICY.latency_seconds[1]}})
    if not eco:
        _mark_pareto(rows)
    return rows, norm


def score_ecosystem(models, profile, prefs, *, config=None, order=None):
    return build_rows(models, profile, prefs, config=config, order=order)


def score_candidates(models: List[ModelMetadata], profile: QueryProfileV2, prefs: ResolvedPreferences, *,
                     observed: Optional[Dict[str, ObservedStats]] = None, learning: Optional[Dict[str, float]] = None,
                     config: Optional[ScoringConfig] = None, evidence_store=None, today=None) -> Tuple[List[CandidateScore], NormalizationDetails]:
    if not models:
        raise ValueError("score_candidates requires at least one candidate model")
    return build_rows(models, profile, prefs, observed=observed, learning=learning, config=config, evidence_store=evidence_store, today=today)


MAX_LISTED_DOMINATORS = 5


def _mark_pareto(rows: List[CandidateScore]) -> None:
    """Pareto dominance over the objective utilities.

    A candidate is dominated only by one that is *comparable*: both have known values for exactly the same objectives.
    Candidates with different missing data are incomparable and are never marked dominated because of what is unknown.
    Candidates are bucketed by their known-objective signature and each bucket is scanned in descending order of summed
    utility (a dominator always has a strictly larger sum), so the cost is near-linear for realistic catalogues.
    At most MAX_LISTED_DOMINATORS dominators are named per candidate (so the list is a sample, not a count)."""
    buckets: Dict[tuple, List[tuple]] = {}
    for r in rows:
        sig = tuple(d for d in _PARETO_DIMS if r.utilities.get(d) is not None)
        vec = tuple(r.utilities[d] for d in sig)
        buckets.setdefault(sig, []).append((sum(vec), r.model_id, vec, r))
    for sig, items in buckets.items():
        items.sort(key=lambda t: (-t[0], t[1]))
        for i, (tot, _mid, vec, r) in enumerate(items):
            dom: List[str] = []
            for tot2, mid2, vec2, _r2 in items[:i]:
                if tot2 <= tot:                       # equal sums cannot strictly dominate; later items are no larger
                    break
                if all(a >= b for a, b in zip(vec2, vec)):
                    dom.append(mid2)
                    if len(dom) >= MAX_LISTED_DOMINATORS:
                        break
            r.dominated_by, r.pareto_optimal = dom, not dom


SCORE_DECIMALS = POLICY.score_decimals


def _tie_key(r: CandidateScore):
    """Exact-order key. Applies feedback, preferred provider, known cost, list order and id ONLY between candidates whose evidence-credited scores are exactly equal."""
    return decision.order_key(r.robust_score, r.learning_adjustment, r.preferred_provider, r.estimated_cost_usd, r.editorial_order, r.model_id)


def _same_evidence(a: CandidateScore, b: CandidateScore) -> bool:
    return round(a.robust_score, SCORE_DECIMALS) == round(b.robust_score, SCORE_DECIMALS)


def select(rows: List[CandidateScore], prefs: ResolvedPreferences, profile: QueryProfileV2, config: Optional[ScoringConfig] = None) -> Selection:
    cfg = config or ScoringConfig()
    if not rows:
        return Selection(status="no_eligible_candidates", decision_status="no_eligible_candidates", decision_reason=decision.status(
            n=0, tied_top=0, strict_leader=False, gaps_top=[], margin=None, feedback_decided=False, needs_clarification=False)[1], caveats=["No candidate satisfied the hard constraints."])
    ordered = sorted(rows, key=_tie_key)
    for i, r in enumerate(ordered, 1):
        r.rank = i
    rows[:] = ordered
    top = ordered[0]
    tied = [r for r in ordered if _same_evidence(r, top)]
    fb_tied = [r for r in tied if round(r.learning_adjustment, SCORE_DECIMALS) == round(top.learning_adjustment, SCORE_DECIMALS)]
    feedback_decided = len(tied) > 1 and len(fb_tied) == 1
    margin = round(top.robust_score - ordered[1].robust_score, 5) if len(ordered) > 1 else None
    tie_note: Optional[str] = None
    if len(ordered) > 1 and _same_evidence(top, ordered[1]):
        a, b = _tie_key(top), _tie_key(ordered[1])
        labels = ["evidence-credited score", "your own past feedback", "preferred provider", "lower estimated cost", "approved-list order (scores are exactly equal)", "model id (final deterministic fallback)"]
        tie_note = next((labels[i] for i in range(6) if a[i] != b[i]), labels[5])

    wm, wm_rival = None, None
    if len(ordered) > 1 and top.score_weights and len(fb_tied) == 1 and len(tied) == 1:
        wm, wm_rival = min_weight_margin([(r.model_id, r.adjusted_values) for r in ordered], top.score_weights)
        wm = round(wm, 4) if wm is not None else None
    elif len(ordered) > 1 and len(tied) > 1:
        wm, wm_rival = 0.0, ordered[1].model_id
    stability = None if len(ordered) < 2 else (1.0 if wm is None else min(1.0, wm / cfg.safe_weight_shift))

    dstatus, dreason = decision.status(n=len(ordered), tied_top=len(fb_tied), strict_leader=len(tied) == 1, gaps_top=top.evidence_gaps, margin=wm, feedback_decided=feedback_decided,
                                       needs_clarification=profile.needs_clarification)
    # who cannot be separated from the selected candidate
    alts: List[str] = []
    if dstatus == "indistinguishable":
        alts = [r.model_id for r in fb_tied if r.model_id != top.model_id]
    elif dstatus in ("qualified", "insufficient_evidence") and len(ordered) > 1 and top.score_weights:
        for r in ordered[1:]:
            if _same_evidence(r, top):
                alts.append(r.model_id)
                continue
            m_ = weight_margin(top.adjusted_values, r.adjusted_values, top.score_weights)
            if m_ is not None and m_ < cfg.safe_weight_shift:
                alts.append(r.model_id)
    not_ranked: List[Dict[str, str]] = []
    for d in ALL_OBJECTIVES:
        if d in top.score_weights:
            continue
        e = top.evidence.get(d)
        label = "speed" if d == "latency" else ("task fit" if d == FIT else d)
        if e is None:
            continue
        why = (f"evidence is {e.tier.replace('_', ' ')}" + (f" ({e.freshness})" if e.freshness in ("stale", "undated") else "") + "; shown, not used to rank" if e.tier in ("unknown", "unverified_estimate")
               else "you did not prioritise it; shown, not used to rank")
        not_ranked.append({"objective": label, "tier": e.tier, "reason": why})

    caveats: List[str] = []
    if dstatus == "indistinguishable":
        names = ", ".join(r.model_name for r in fb_tied[:6])
        caveats.append(f"These products are equally suitable on the evidence that may rank them: {names}. The order shown follows a fixed deterministic rule, not a measured difference.")
    elif dstatus == "insufficient_evidence":
        caveats.append(dreason)
    elif dstatus == "qualified":
        caveats.append(dreason)
    weak = [n["objective"] for n in not_ranked if n["tier"] in ("unknown", "unverified_estimate")]
    if weak:
        caveats.append("Not evaluated for lack of verified evidence: " + ", ".join(weak) + ".")
    if len(ordered) == 1:
        caveats.append("Only one candidate satisfied the constraints, so there was nothing to compare it against.")
    if profile.needs_clarification:
        caveats.append("The query needs clarification; treat this recommendation as provisional.")
    if margin is not None and 0 < margin < cfg.near_tie_margin:
        caveats.append("The top two products score almost identically; treat them as comparable options.")

    base = dict(selected_model_id=top.model_id, runner_up_ids=[r.model_id for r in ordered[1:4]], status="selected" if not profile.needs_clarification else "needs_clarification",
                tie_break_applied=tie_note, score_margin=margin, weight_margin=wm, weight_margin_rival=wm_rival, decision_status=dstatus, decision_reason=dreason,
                alternative_ids=alts, evidence_gaps=list(top.evidence_gaps), not_ranked=not_ranked)
    if all(r.ecosystem_category is not None for r in ordered):
        value, comps, cap_notes = ecosystem_confidence(top, ordered[1] if len(ordered) > 1 else None, profile)
        if dstatus == "insufficient_evidence":
            value = min(value, 0.45)
            cap_notes.append("capped at 0.45: a priority you stated cannot be verified")
        level = "high" if value >= 0.75 else "medium" if value >= 0.5 else "low"
        caveats += [n.capitalize() + "." for n in cap_notes]
        return Selection(**base, weight_stability=None, confidence_level=level, confidence_value=round(value, 3), confidence_formula=SELECTION_CONFIDENCE_FORMULA, confidence_components=comps, caveats=caveats)
    margin_part = min(1.0, (margin or 0.0) / MARGIN_FULL) if margin is not None else 0.5
    value = 0.5 * top.confidence + 0.3 * (stability if stability is not None else 0.5) + 0.2 * margin_part
    if profile.needs_clarification:
        value = min(value, 0.45)
    if dstatus == "insufficient_evidence":
        value = min(value, 0.45)
    level = "high" if value >= 0.75 else "medium" if value >= 0.5 else "low"
    return Selection(**base, weight_stability=round(stability, 3) if stability is not None else None, confidence_level=level, confidence_value=round(value, 3), caveats=caveats)
