"""Generation-based retention. A pure function over ``CatalogState``.

Per lineage (developer:family:track) the latest TWO verified generations are retained; older
verified generations become superseded. Everything else is conservative: ambiguous or
conflicting evidence yields ``pending_review`` and never a destructive transition, and a lineage
can never be left without a retained generation. Variants of a retained generation are retained.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.services.catalog.state import (CatalogState, Event, GenerationRecord, LineageRecord, R_RETAINED, R_REVIEW, R_SUPERSEDED, R_UNMANAGED,
                                         R_UNVERIFIED, L_ACTIVE, L_DISCOVERED, L_PENDING, L_SUPERSEDED, V_CORROBORATED, V_RANK, iso, parse_iso)

KEEP_GENERATIONS = 2
CHRONOLOGY_TOLERANCE = timedelta(days=30)
CHRONOLOGY_WINDOW = 3
_MIN = V_RANK[V_CORROBORATED]


def _is_verified(verification: str) -> bool:
    return V_RANK.get(verification, 0) >= _MIN


def _set_model(rec, retention: str, reason: Optional[str], ts: str, events: list) -> None:
    old = rec.retention
    rec.retention, rec.retention_reason = retention, reason
    if retention == R_SUPERSEDED:
        life = L_SUPERSEDED
        if rec.superseded_at is None:
            rec.superseded_at = ts
    elif retention in (R_RETAINED, R_UNMANAGED):
        life = L_ACTIVE
        rec.superseded_at = None
    elif retention == R_REVIEW:
        life = rec.lifecycle if rec.lifecycle in (L_ACTIVE, L_SUPERSEDED) else L_PENDING
    else:
        life = L_PENDING if rec.lifecycle in (L_DISCOVERED, L_PENDING) else rec.lifecycle
    if life != rec.lifecycle:
        events.append(Event("lifecycle_changed", "model", rec.canonical_key, ts, rec.lifecycle, life, reason))
        rec.lifecycle = life
    if old != retention:
        etype = {R_SUPERSEDED: "model_superseded", R_RETAINED: "model_retained", R_REVIEW: "model_review_required"}.get(retention, "retention_changed")
        events.append(Event(etype, "model", rec.canonical_key, ts, old, retention, reason))


def _set_gen(g, retention: str, reason: Optional[str], ts: str, events: list) -> None:
    if g.retention != retention:
        etype = {R_SUPERSEDED: "generation_superseded", R_RETAINED: "generation_retained", R_REVIEW: "generation_review_required"}.get(retention, "generation_changed")
        events.append(Event(etype, "generation", g.generation_key, ts, g.retention, retention, reason))
    g.retention, g.retention_reason = retention, reason


def apply_retention(state: CatalogState, now: datetime) -> list:
    events: list = []
    ts = iso(now)
    by_lineage: dict = {}
    for rec in state.models.values():
        by_lineage.setdefault(rec.lineage_key, []).append(rec)

    for lineage, models in by_lineage.items():
        first = models[0]
        lin = state.lineages.get(lineage) or LineageRecord(lineage, first.developer, first.family, first.track)
        state.lineages[lineage] = lin
        lin.review_reason = None

        managed = [m for m in models if m.generation_kind != "none" and m.generation_key]
        for m in models:
            if m.generation_kind == "none" or not m.generation_key:
                _set_model(m, R_UNMANAGED if _is_verified(m.verification) else R_UNVERIFIED, "no generation marker; never retired automatically", ts, events)

        gens: dict = {}
        for m in managed:
            g = state.generations.get(m.generation_key)
            if g is None:
                g = GenerationRecord(m.generation_key, lineage, m.generation_kind, m.generation_label or "", [])
                state.generations[m.generation_key] = g
            gens.setdefault(m.generation_key, []).append(m)

        # lineage-level ambiguity: mixed version/date schemes or low-confidence parses => no destructive action here
        kinds = {m.generation_kind for m in managed}
        ambiguous = len(kinds) > 1 or any(m.classification_confidence == "low" for m in managed)
        info = {}
        for gk, ms in gens.items():
            g = state.generations[gk]
            ver = max(ms, key=lambda m: V_RANK.get(m.verification, 0)).verification
            dates = [m.released_at for m in ms if m.released_at]
            g.first_released_at = min(dates) if dates else None
            g.verification, g.model_count = ver, len(ms)
            g.sort_key = list(ms[0].generation_sort)
            info[gk] = g
        verified = [g for g in info.values() if _is_verified(g.verification)]
        verified.sort(key=lambda g: tuple(g.sort_key), reverse=True)

        # chronology cross-check: a higher version released clearly BEFORE a lower one is contradictory evidence
        conflict = None
        dated = [g for g in verified[:CHRONOLOGY_WINDOW] if g.first_released_at]     # old/odd rows far down the lineage must not freeze newer generations
        for i, hi in enumerate(dated):
            for lo in dated[i + 1:]:
                if parse_iso(hi.first_released_at) + CHRONOLOGY_TOLERANCE < parse_iso(lo.first_released_at):
                    conflict = f"{hi.label} is numbered higher than {lo.label} but was released earlier"
        if ambiguous or conflict:
            lin.review_reason = conflict or "generation could not be established confidently or version schemes are mixed"
            for gk, ms in gens.items():
                g = state.generations[gk]
                for m in ms:
                    if m.retention in (R_RETAINED, R_SUPERSEDED):
                        continue                                    # never change a settled state under doubt
                    _set_model(m, R_REVIEW, lin.review_reason, ts, events)
                if g.retention not in (R_RETAINED, R_SUPERSEDED):
                    _set_gen(g, R_REVIEW, lin.review_reason, ts, events)
            continue

        keep = {g.generation_key for g in verified[:KEEP_GENERATIONS]}
        for gk, ms in gens.items():
            g = state.generations[gk]
            if not _is_verified(g.verification):
                _set_gen(g, R_UNVERIFIED, "awaiting verification", ts, events)
                for m in ms:
                    _set_model(m, R_UNVERIFIED, "generation not yet verified", ts, events)
            elif gk in keep:
                _set_gen(g, R_RETAINED, f"one of the latest {KEEP_GENERATIONS} verified generations", ts, events)
                for m in ms:
                    _set_model(m, R_RETAINED, g.retention_reason, ts, events)
            else:
                _set_gen(g, R_SUPERSEDED, "superseded by newer verified generations", ts, events)
                for m in ms:
                    _set_model(m, R_SUPERSEDED, g.retention_reason, ts, events)
    return events



def assert_invariants(state: CatalogState) -> list:
    """Returns violations; the engine refuses to publish a state that has any."""
    bad = []
    by_lineage: dict = {}
    for m in state.models.values():
        by_lineage.setdefault(m.lineage_key, []).append(m)
    for lin, ms in by_lineage.items():
        managed_verified = [m for m in ms if m.generation_key and _is_verified(m.verification)]
        if managed_verified and not any(m.retention == R_RETAINED for m in ms) and not (state.lineages.get(lin) and state.lineages[lin].review_reason):
            bad.append(f"{lin}: no retained generation")
        keys = {m.generation_key for m in ms if m.retention == R_RETAINED}
        if len(keys) > KEEP_GENERATIONS:
            bad.append(f"{lin}: {len(keys)} retained generations")
    return bad
