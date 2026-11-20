"""Turn a registry entry (plus optional observed telemetry and evidence records) into one evidenced Cell per objective.

Rule of thumb: a value may rank only if it is documented, measured, or an estimate with a named process. Hand-set editorial estimates and
anything unavailable are carried for DISPLAY (value=None, display_value=<the number>) and never enter a score.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, List, Optional

from app.schemas.model import ModelMetadata
from app.services.routing_engine import normalization as N
from app.services.routing_engine.evidence import (
    Cell, EvidenceRecord, T0, T1, T1U, T2, T3, effective_tier, freshness, records_for,
)
from app.services.routing_engine.observed import MIN_SAMPLES, ObservedStats
from app.services.routing_engine.policy import POLICY, ErPcrPolicy
from app.services.routing_engine.types import QueryProfileV2

PRICING_UTILITY = {"completely_free": 1.0, "self_hosted_open_weight": 1.0, "free_tier_limited": 0.75, "pay_as_you_go": 0.5, "paid_subscription": 0.3}
ALLOWED_PRIVACY = {"provider_documented_restricted", "customer_controlled"}
MEASURED = {"measured", "observed", "benchmark", "provider_reported"}
DOCUMENTED = {"provider_published", "vendor_published", "curated_pricing_category"}


def _from_record(dim: str, r: EvidenceRecord, kind: str, policy: ErPcrPolicy, today: Optional[date]) -> Cell:
    fr = freshness(r.date, policy.freshness_for(kind), today)
    tier = effective_tier(r.tier, fr)
    lo, hi = (r.uncertainty or (None, None))
    note = r.rationale or r.method or ""
    if lo is not None:
        note = (note + " " if note else "") + f"source-supplied range [{lo}, {hi}]"
    return Cell(dim, N.unit_interval(r.value) if tier >= T1 else None, tier, display_value=r.value, unit=r.unit, source=r.source, date=r.date, freshness=fr,
                note=note, sample_size=r.sample_size)


def _display(dim: str, v: Optional[float], unit: str, note: str) -> Cell:
    if v is None or not math.isfinite(v):
        return Cell(dim, None, T0, note="no value available")
    return Cell(dim, None, T1U, display_value=round(float(v), 4), unit=unit, freshness="n/a", note=note)


def objective_cells(m: ModelMetadata, profile: QueryProfileV2, *, ecosystem: bool, observed: Optional[ObservedStats] = None, request_cost_usd: Optional[float] = None,
                    store: Optional[Dict[str, List[EvidenceRecord]]] = None, policy: ErPcrPolicy = POLICY, today: Optional[date] = None) -> Dict[str, Cell]:
    store = store or {}
    task = getattr(profile, "task_type", None)
    prov = m.metric_provenance or {}
    src = m.provider_source or m.external_url
    cells: Dict[str, Cell] = {}

    def rec(metric: str, kind: str) -> Optional[Cell]:
        rs = records_for(store, m.model_id, task, metric)
        if not rs:
            return None
        best = max((_from_record(metric, r, kind, policy, today) for r in rs), key=lambda c: (c.tier, c.sample_size or 0))
        return best

    # quality: only benchmark/measured provenance may rank
    c = rec("quality", "benchmark")
    if c is None:
        q = m.estimated_quality
        if q is not None and prov.get("quality") in {"benchmark", "measured"}:
            fr = freshness(m.last_verified_at, policy.freshness_for("benchmark"), today)
            c = Cell("quality", N.unit_interval(q), effective_tier(T2, fr), display_value=q, unit="0-1 benchmark score", source=src, date=m.last_verified_at, freshness=fr)
        else:
            c = _display("quality", q, "0-1 editorial estimate", "Hand-set estimate with no named source or method; shown, not used to rank")
    cells["quality"] = c

    # cost
    c = rec("cost", "pricing")
    if c is None:
        if ecosystem and m.pricing_category in PRICING_UTILITY:
            c = Cell("cost", PRICING_UTILITY[m.pricing_category], T2, display_value=PRICING_UTILITY[m.pricing_category], unit="0-1 access class", source=src, date=m.last_verified_at,
                     freshness=freshness(m.last_verified_at, policy.freshness_for("pricing"), today), note=f"documented access class: {m.pricing_category.replace('_', ' ')} (not a price)")
            c.tier = effective_tier(c.tier, c.freshness)
        elif not ecosystem and request_cost_usd is not None and (m.metric_provenance or {}).get("pricing", "provider_published") in DOCUMENTED | {"unavailable"} and m.input_price_per_million is not None:
            fr = freshness(m.last_verified_at, policy.freshness_for("pricing"), today)
            u = N.cost_utility(request_cost_usd)
            c = Cell("cost", u, effective_tier(T2, fr), display_value=request_cost_usd, unit="USD/request (estimated tokens x published unit prices)", source=src, date=m.last_verified_at, freshness=fr,
                     note="estimated from published unit prices and estimated token counts; not a billed amount")
        elif m.estimated_cost is not None:
            c = _display("cost", None if m.estimated_cost is None else 1.0 - m.estimated_cost, "0-1 registry estimate", "Registry-normalised estimate, not a published price; shown, not used to rank")
        else:
            c = Cell("cost", None, T0, note="no published pricing")
    cells["cost"] = c

    # latency: observed telemetry, then measured/provider-reported, else display only
    c = rec("latency", "benchmark")
    if c is None:
        if observed is not None and observed.samples >= MIN_SAMPLES and observed.latency_p50_seconds:
            c = Cell("latency", N.latency_utility(observed.latency_p50_seconds), T3, display_value=observed.latency_p50_seconds, unit="seconds (observed p50)", source="AI Compass telemetry",
                     freshness="fresh", note=f"{observed.samples} observed requests", sample_size=observed.samples)
        elif m.avg_latency_seconds and m.avg_latency_seconds > 0 and prov.get("latency") in MEASURED:
            fr = freshness(m.last_verified_at, policy.freshness_for("benchmark"), today)
            c = Cell("latency", N.latency_utility(m.avg_latency_seconds), effective_tier(T2, fr), display_value=m.avg_latency_seconds, unit="seconds", source=src, date=m.last_verified_at, freshness=fr)
        elif m.avg_latency_seconds and m.avg_latency_seconds > 0 and not ecosystem:
            c = _display("latency", N.latency_utility(m.avg_latency_seconds), "0-1 speed from an estimated latency", "Estimated latency, not measured; shown, not used to rank")
        elif m.estimated_latency is not None:
            c = _display("latency", m.estimated_latency if ecosystem else 1.0 - m.estimated_latency, "0-1 editorial estimate", "Hand-set estimate with no named source or method; shown, not used to rank")
        else:
            c = Cell("latency", None, T0, note="no latency data")
    cells["latency"] = c

    # reliability
    c = rec("reliability", "telemetry")
    if c is None:
        if observed is not None and observed.samples >= MIN_SAMPLES and observed.success_lower_bound is not None:
            c = Cell("reliability", N.unit_interval(observed.success_lower_bound), T3, display_value=observed.success_lower_bound, unit="Wilson lower bound of observed success", source="AI Compass telemetry",
                     freshness="fresh", note=f"{observed.successes}/{observed.samples} successful in {observed.window_days} days", sample_size=observed.samples)
        elif m.reliability is not None and prov.get("reliability") in {"measured", "observed"}:
            fr = freshness(m.last_verified_at, policy.freshness_for("telemetry"), today)
            c = Cell("reliability", N.unit_interval(m.reliability), effective_tier(T2, fr), display_value=m.reliability, unit="0-1 measured success rate", source=src, date=m.last_verified_at, freshness=fr)
        else:
            c = _display("reliability", m.reliability, "0-1 editorial estimate", "Hand-set estimate with no named source or method; shown, not used to rank")
    cells["reliability"] = c

    # risk: exposure of the user's data. Documented restricted handling -> no exposure; otherwise exposure equals the query's own sensitivity (deterministic lexical analysis).
    c = rec("risk", "privacy")
    if c is None:
        if m.data_handling_status in ALLOWED_PRIVACY:
            fr = freshness(m.last_verified_at, policy.freshness_for("privacy"), today)
            c = Cell("risk", N.risk_suitability(0.0), effective_tier(T2, fr), display_value=1.0, unit="0-1 data-handling suitability", source=src, date=m.last_verified_at, freshness=fr,
                     note="documented restricted data handling")
        else:
            c = Cell("risk", N.risk_suitability(profile.risk.score), T1, display_value=N.risk_suitability(profile.risk.score), unit="0-1 data-handling suitability", freshness="n/a",
                     note="data handling not documented; exposure taken as the query's own sensitivity (lexical analysis)")
    cells["risk"] = c
    return cells
