"""Multi-objective scoring and selection (SCORING_VERSION 2.0.0).

Methodology
-----------
Hard constraints are applied before this module (``filtering``). Here every eligible
candidate receives a utility in [0, 1] per objective, higher always better:

* quality      registry quality estimate (provenance-aware) x task discount, plus a bounded
               feedback adjustment. Discount = (1 - D) + D * task_fit, D = TASK_FIT_DISCOUNT,
               because a general quality figure is not a universal measure for every task.
* cost         estimated USD per request (published prices x estimated tokens). When every
               candidate is priced: log-scale min-max across candidates. Otherwise the registry's
               normalised cost estimate (1 - value) is used. Unknown cost is missing, never zero.
* latency      observed p50 seconds, or registry-measured seconds when *all* candidates have them
               (log min-max); otherwise the registry's normalised estimate (1 - value).
* reliability  Wilson lower bound of observed success rate when >= MIN_SAMPLES samples exist,
               otherwise the registry estimate (low confidence).
* risk         1 - max(model risk, exposure risk). Exposure risk equals the query's sensitivity score
               unless the provider documents restricted data handling.
* preference_alignment (task fit)  share of the query's intents the model declares support for
               (0.7 primary + 0.3 secondary coverage). Provider preferences act as a tie-breaker.

Missing data: policy ``pessimistic`` (default) assigns utility 0 and confidence 0 for that
objective and flags it, so a model cannot win through incomplete metadata.

Overall utility U = sum_d w_d * u_d. Because estimates are uncertain, candidates are ranked by the
robust score R = sum_d w_d * max(0, u_d - (1 - c_d) * RHO), a pessimistic lower bound, where c_d is
the evidence confidence of objective d. Ties (|dR| < eps) break by: preferred provider, higher
confidence, lower known cost, then model id. Pareto dominance (over quality/cost/latency/
reliability/risk) is reported, and weight stability (winner under +/-20% perturbation of each
weight) feeds the decision confidence.
"""
import math
from typing import Dict, List, Optional, Tuple

from app.schemas.model import ModelMetadata
from app.services.routing_engine.filtering import declared_latency_seconds, estimate_request_cost, MEASURED_LATENCY_PROVENANCE
from app.services.routing_engine.observed import MIN_SAMPLES, ObservedStats
from app.services.routing_engine.preferences import DIMENSIONS
from app.services.routing_engine.types import (
    CandidateScore, MetricEvidence, NormalizationDetails, QueryProfileV2, ResolvedPreferences, ScoringConfig, Selection,
)

TASK_FIT_DISCOUNT = 0.4
_PROVENANCE_CONFIDENCE = {"measured": 1.0, "observed": 1.0, "benchmark": 0.9, "provider_published": 0.85, "estimated": 0.6, "unavailable": 0.0}
_ALLOWED_PRIVACY = {"provider_documented_restricted", "customer_controlled"}
_PARETO_DIMS = ("quality", "cost", "latency", "reliability", "risk")


def _prov_conf(model: ModelMetadata, key: str) -> Tuple[str, float]:
    prov = (model.metric_provenance or {}).get(key, "estimated")
    return prov, _PROVENANCE_CONFIDENCE.get(prov, 0.5)


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


def _log_minmax_utility(values: Dict[str, float]) -> Dict[str, float]:
    floor = 1e-6
    logs = {k: math.log(max(v, floor)) for k, v in values.items()}
    lo, hi = min(logs.values()), max(logs.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in values}
    return {k: round(1.0 - (v - lo) / (hi - lo), 6) for k, v in logs.items()}


def score_candidates(models: List[ModelMetadata], profile: QueryProfileV2, prefs: ResolvedPreferences, *,
                     observed: Optional[Dict[str, ObservedStats]] = None, learning: Optional[Dict[str, float]] = None,
                     config: Optional[ScoringConfig] = None) -> Tuple[List[CandidateScore], NormalizationDetails]:
    if not models:
        raise ValueError("score_candidates requires at least one candidate model")
    cfg = config or ScoringConfig()
    observed = observed or {}
    learning = learning or {}
    notes: List[str] = []
    w = prefs.weights

    usd = {m.model_id: estimate_request_cost(m, profile.tokens.input_tokens, profile.tokens.output_tokens) for m in models}
    all_priced = all(v is not None for v in usd.values())
    cost_basis = "usd_estimate_log_minmax" if all_priced else "registry_estimate"
    usd_u = _log_minmax_utility({k: v for k, v in usd.items() if v is not None}) if all_priced else {}
    if not all_priced:
        notes.append("Not every candidate publishes pricing, so cost uses the registry's normalised estimate for comparability.")

    secs: Dict[str, Tuple[Optional[float], str]] = {}
    for m in models:
        o = observed.get(m.model_id)
        p50 = o.latency_p50_seconds if o and o.samples >= MIN_SAMPLES else None
        secs[m.model_id] = declared_latency_seconds(m, p50)
    lat_measured = all(s is not None and b in {"observed_p50", "registry_measured"} for s, b in secs.values())
    lat_basis = "seconds_log_minmax" if lat_measured else "registry_estimate"
    lat_u = _log_minmax_utility({k: s for k, (s, _b) in secs.items() if s is not None}) if lat_measured else {}
    if not lat_measured:
        notes.append("Latency values are registry estimates, not measurements, unless observed history exists for every candidate.")

    results: List[CandidateScore] = []
    for m in models:
        ev: Dict[str, MetricEvidence] = {}
        util: Dict[str, Optional[float]] = {}
        fit = task_fit(m, profile)

        # quality
        qprov, qconf = _prov_conf(m, "quality")
        if m.estimated_quality is None or not math.isfinite(m.estimated_quality):
            ev["quality"] = MetricEvidence(dimension="quality", provenance="unavailable", note="No quality estimate in the registry")
            util["quality"] = None
        else:
            discount = (1 - TASK_FIT_DISCOUNT) + TASK_FIT_DISCOUNT * (fit if fit is not None else 0.0)
            bonus = max(-0.2, min(0.2, learning.get(m.model_id, 0.0)))
            util["quality"] = max(0.0, min(1.0, m.estimated_quality * discount + bonus))
            ev["quality"] = MetricEvidence(dimension="quality", raw_value=m.estimated_quality, unit="0-1 registry estimate", provenance=qprov, confidence=qconf, missing=False,
                                           note=f"task discount x{discount:.2f}" + (f", feedback adjustment {bonus:+.3f}" if bonus else ""))
        # cost
        cprov, cconf = _prov_conf(m, "cost")
        c = usd[m.model_id]
        if all_priced and c is not None:
            util["cost"] = usd_u[m.model_id]
            ev["cost"] = MetricEvidence(dimension="cost", raw_value=c, unit="USD/request (estimated tokens)", provenance=_prov_conf(m, "pricing")[0], confidence=min(0.85, _prov_conf(m, "pricing")[1]) * 0.9, missing=False,
                                        note=f"{profile.tokens.input_tokens} in + {profile.tokens.output_tokens} out tokens (estimates)")
        elif m.estimated_cost is not None:
            util["cost"] = 1.0 - m.estimated_cost
            ev["cost"] = MetricEvidence(dimension="cost", raw_value=m.estimated_cost, unit="0-1 registry estimate", provenance=cprov, confidence=min(cconf, 0.6), missing=False, note="registry estimate; not a billed price")
        else:
            util["cost"] = None
            ev["cost"] = MetricEvidence(dimension="cost", provenance="unavailable", note="No pricing or cost estimate")
        # latency
        sec, basis = secs[m.model_id]
        lprov, lconf = _prov_conf(m, "latency")
        if lat_measured and sec is not None:
            util["latency"] = lat_u[m.model_id]
            ev["latency"] = MetricEvidence(dimension="latency", raw_value=sec, unit="seconds", provenance=basis, confidence=1.0 if basis == "observed_p50" else 0.8, missing=False)
        elif m.estimated_latency is not None:
            util["latency"] = 1.0 - m.estimated_latency
            ev["latency"] = MetricEvidence(dimension="latency", raw_value=m.estimated_latency, unit="0-1 registry estimate", provenance=lprov, confidence=min(lconf, 0.6), missing=False, note="registry estimate; not measured")
        else:
            util["latency"] = None
            ev["latency"] = MetricEvidence(dimension="latency", provenance="unavailable", note="No latency data")
        # reliability
        o = observed.get(m.model_id)
        if o and o.samples >= MIN_SAMPLES and o.success_lower_bound is not None:
            util["reliability"] = o.success_lower_bound
            ev["reliability"] = MetricEvidence(dimension="reliability", raw_value=o.success_lower_bound, unit="Wilson lower bound", provenance="observed", confidence=0.5 + 0.5 * min(1.0, o.samples / 50.0), missing=False,
                                               note=f"{o.successes}/{o.samples} successful in {o.window_days} days")
        elif m.reliability is not None:
            rprov, rconf = _prov_conf(m, "reliability")
            util["reliability"] = m.reliability
            ev["reliability"] = MetricEvidence(dimension="reliability", raw_value=m.reliability, unit="0-1 registry estimate", provenance=rprov, confidence=min(rconf, 0.6), missing=False, note="registry estimate; no observed history yet")
        else:
            util["reliability"] = None
            ev["reliability"] = MetricEvidence(dimension="reliability", provenance="unavailable", note="No reliability data")
        # risk
        if m.risk_level is None:
            util["risk"] = None
            ev["risk"] = MetricEvidence(dimension="risk", provenance="unavailable", note="No model risk estimate")
        else:
            rkprov, rkconf = _prov_conf(m, "risk")
            exposure = 0.0 if m.data_handling_status in _ALLOWED_PRIVACY else profile.risk.score
            util["risk"] = 1.0 - max(m.risk_level, exposure)
            ev["risk"] = MetricEvidence(dimension="risk", raw_value=max(m.risk_level, exposure), unit="0-1 (lower is better)", provenance=rkprov, confidence=min(rkconf, 0.6), missing=False,
                                        note=("data handling not documented; exposure risk = query sensitivity" if exposure else "model risk estimate"))
        # task fit
        if fit is None:
            util["preference_alignment"] = None
            ev["preference_alignment"] = MetricEvidence(dimension="preference_alignment", provenance="unavailable", note="Model declares no tasks or capabilities")
        else:
            util["preference_alignment"] = fit
            ev["preference_alignment"] = MetricEvidence(dimension="preference_alignment", raw_value=fit, unit="0-1 task fit", provenance="registry_declared_capabilities", confidence=0.8, missing=False)

        missing = [d for d in DIMENSIONS if util[d] is None]
        eff = {d: (util[d] if util[d] is not None else 0.0) for d in DIMENSIONS}
        conf = {d: (ev[d].confidence if util[d] is not None else 0.0) for d in DIMENSIONS}
        U = sum(w[d] * eff[d] for d in DIMENSIONS)
        R = sum(w[d] * max(0.0, eff[d] - (1 - conf[d]) * cfg.uncertainty_penalty) for d in DIMENSIONS)
        results.append(CandidateScore(
            model_id=m.model_id, model_name=m.model_name, provider=m.provider, entry_type=m.entry_type, executable=m.entry_type == "inference_model" and m.adapter_compatible,
            utilities={d: (round(util[d], 4) if util[d] is not None else None) for d in DIMENSIONS}, contributions={d: round(w[d] * eff[d], 5) for d in DIMENSIONS},
            evidence=ev, missing_dimensions=missing, confidence=round(sum(w[d] * conf[d] for d in DIMENSIONS), 4), utility=round(U, 5), robust_score=round(R, 5),
            estimated_cost_usd=c, learning_adjustment=round(max(-0.2, min(0.2, learning.get(m.model_id, 0.0))), 4), task_fit=fit or 0.0,
            preferred_provider=m.provider.lower() in prefs.preferred_providers, metadata_status=m.metadata_status))
    _mark_pareto(results)
    norm = NormalizationDetails(cost_basis=cost_basis, cost_method="log10-scale min-max over candidates" if all_priced else "1 - registry normalised estimate",
                                latency_basis=lat_basis, uncertainty_penalty=cfg.uncertainty_penalty, missing_policy=cfg.missing_policy, notes=notes,
                                ranges={"cost_usd": {"min": min((v for v in usd.values() if v is not None), default=None), "max": max((v for v in usd.values() if v is not None), default=None)}})
    return results, norm


def _mark_pareto(rows: List[CandidateScore]) -> None:
    def vec(r: CandidateScore) -> List[float]:
        return [(r.utilities.get(d) if r.utilities.get(d) is not None else -1.0) for d in _PARETO_DIMS]
    vs = {r.model_id: vec(r) for r in rows}
    for r in rows:
        dom = [o.model_id for o in rows if o.model_id != r.model_id and all(a >= b for a, b in zip(vs[o.model_id], vs[r.model_id])) and any(a > b for a, b in zip(vs[o.model_id], vs[r.model_id]))]
        r.dominated_by, r.pareto_optimal = dom, not dom


def _robust(rows: List[CandidateScore], weights: Dict[str, float], rho: float) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in rows:
        total = 0.0
        for d in DIMENSIONS:
            u = r.utilities.get(d)
            if u is None:
                continue
            total += weights[d] * max(0.0, u - (1 - r.evidence[d].confidence) * rho)
        out[r.model_id] = total
    return out


def _tie_key(r: CandidateScore):
    return (not r.preferred_provider, -r.confidence, r.estimated_cost_usd if r.estimated_cost_usd is not None else float("inf"), r.model_id)


def _winner(rows: List[CandidateScore], scores: Dict[str, float], eps: float) -> CandidateScore:
    """Best by score; candidates within `eps` of the best are a near-tie and are resolved by the same deterministic
    tie rules as the real selection, so the stability figure measures what selection actually does."""
    best = max(scores[r.model_id] for r in rows)
    tied = [r for r in rows if best - scores[r.model_id] < eps]
    return min(tied, key=_tie_key)


def select(rows: List[CandidateScore], prefs: ResolvedPreferences, profile: QueryProfileV2, config: Optional[ScoringConfig] = None) -> Selection:
    cfg = config or ScoringConfig()
    if not rows:
        return Selection(status="no_eligible_candidates", caveats=["No candidate satisfied the hard constraints."])
    ordered = sorted(rows, key=lambda r: (-r.robust_score, _tie_key(r)))
    tie_note: Optional[str] = None
    if len(ordered) > 1 and abs(ordered[0].robust_score - ordered[1].robust_score) < cfg.tie_epsilon:
        tied = [r for r in ordered if abs(r.robust_score - ordered[0].robust_score) < cfg.tie_epsilon]
        tied.sort(key=_tie_key)
        ordered = tied + [r for r in ordered if r not in tied]
        a, b = _tie_key(tied[0]), _tie_key(tied[1])
        labels = ["preferred provider", "higher evidence confidence", "lower estimated cost", "model id (final deterministic fallback)"]
        tie_note = next((labels[i] for i in range(4) if a[i] != b[i]), labels[3])
    for i, r in enumerate(ordered, 1):
        r.rank = i
    rows[:] = ordered
    top = ordered[0]
    margin = round(top.robust_score - ordered[1].robust_score, 5) if len(ordered) > 1 else None

    wins, trials = 0, 0
    if len(ordered) > 1:
        for d in DIMENSIONS:
            for f in (1 - cfg.weight_perturbation, 1 + cfg.weight_perturbation):
                pert = {k: prefs.weights[k] * (f if k == d else 1.0) for k in DIMENSIONS}
                tot = sum(pert.values())
                pert = {k: v / tot for k, v in pert.items()}
                scores = _robust(ordered, pert, cfg.uncertainty_penalty)
                winner = _winner(ordered, scores, cfg.tie_epsilon).model_id
                trials += 1
                wins += winner == top.model_id
        stability = wins / trials
    else:
        stability = None

    caveats: List[str] = []
    est = sum(1 for d in ("quality", "cost", "latency", "reliability", "risk") if top.evidence[d].provenance in {"estimated"} or top.evidence[d].unit.endswith("registry estimate"))
    if est >= 3:
        caveats.append("Most of the selected model's metrics are registry estimates, not measurements.")
    if top.missing_dimensions:
        caveats.append("Missing data for the selected model: " + ", ".join(top.missing_dimensions) + ".")
    if len(ordered) == 1:
        caveats.append("Only one candidate satisfied the constraints, so there was nothing to compare it against.")
    if profile.needs_clarification:
        caveats.append("The query needs clarification; treat this recommendation as provisional.")
    margin_part = min(1.0, (margin or 0.0) / 0.1) if margin is not None else 0.5
    value = 0.5 * top.confidence + 0.3 * (stability if stability is not None else 0.5) + 0.2 * margin_part
    if profile.needs_clarification:
        value = min(value, 0.45)
    level = "high" if value >= 0.75 else "medium" if value >= 0.5 else "low"
    return Selection(selected_model_id=top.model_id, runner_up_ids=[r.model_id for r in ordered[1:4]], status="selected" if not profile.needs_clarification else "needs_clarification",
                     tie_break_applied=tie_note, score_margin=margin, weight_stability=round(stability, 3) if stability is not None else None,
                     confidence_level=level, confidence_value=round(value, 3), caveats=caveats)
