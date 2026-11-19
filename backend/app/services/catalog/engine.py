"""Refresh orchestration: sources -> merge -> availability -> retention -> guarded atomic publication.

Safety properties (each covered by tests):
  * a failed/partial/timed-out source never removes anything; absence is only counted for complete, in-scope responses
  * "missing from a response" is never "discontinued" (needs ABSENCE_THRESHOLD consecutive complete refreshes, and only
    marks the offering unlisted; model retirement comes solely from verified generation succession)
  * the whole new state is committed in one optimistic, versioned transaction (activation + supersession are atomic)
  * a publication that would drop >25% of the published models, or violates invariants, is aborted
  * a refresh that changes nothing writes nothing but source health
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger
from app.services.catalog import announcements, merge as merge_mod
from app.services.catalog import retention as retention_mod
from app.services.catalog.safe_http import FetchError
from app.services.catalog.state import (CatalogState, DeveloperRecord, Event, R_RETAINED, R_SUPERSEDED, R_UNMANAGED, L_REJECTED, SourceState, V_CORROBORATED,
                                         V_RANK, iso, parse_iso)

logger = get_logger(__name__)
_DATA = Path(__file__).resolve().parents[2] / "data"
ABSENCE_THRESHOLD = 3
COMPLETENESS_FLOOR = 0.5
MASS_REMOVAL_LIMIT = 0.25
MAX_BACKOFF_FACTOR = 8


@dataclass
class RefreshReport:
    run_id: str
    trigger: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = "ok"                          # ok | partial | failed | aborted | skipped | conflict
    sources: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    published: bool = False
    version: Optional[int] = None
    notes: list = field(default_factory=list)
    unregistered_developers: dict = field(default_factory=dict)


def registered_developers() -> dict:
    raw = json.loads((_DATA / "developers.json").read_text())
    out = {}
    for d in raw["developers"]:
        out[d["slug"]] = DeveloperRecord(**{k: v for k, v in d.items() if k in DeveloperRecord.__dataclass_fields__})
    return out


def sync_developers(state: CatalogState) -> None:
    """Registry file entries are authoritative for themselves; developers registered at runtime are preserved."""
    for slug, rec in registered_developers().items():
        state.developers[slug] = rec


def is_due(src_state: SourceState, interval_minutes: int, now: datetime) -> bool:
    if not src_state.enabled:
        return False
    if not src_state.last_attempt_at:
        return True
    factor = min(2 ** max(src_state.consecutive_failures, 0), MAX_BACKOFF_FACTOR)
    return now - parse_iso(src_state.last_attempt_at) >= timedelta(minutes=interval_minutes * factor)


def _count_absences(state: CatalogState, src, result, observed_keys: set, ts: str, events: list, run_id: str) -> None:
    """Only a complete, plausibly-sized, in-scope response may count an offering as absent."""
    if src.kind == "documentation_snapshot" or not result.complete or result.not_modified:
        return
    for okey, off in state.offerings.items():
        if off.source_id != src.source_id or okey in observed_keys or not off.listed:
            continue
        model = state.models.get(off.canonical_key)
        if result.scope is not None and (model is None or model.developer not in result.scope):
            continue
        off.consecutive_missing += 1
        if off.consecutive_missing >= ABSENCE_THRESHOLD:
            off.listed = False
            events.append(Event("offering_unlisted", "offering", okey, ts, "listed", "unlisted",
                                f"absent from {off.consecutive_missing} consecutive complete refreshes", run_id))


def _publication(state: CatalogState, ts: str, events: list) -> int:
    published = 0
    for key, m in state.models.items():
        verified = V_RANK.get(m.verification, 0) >= V_RANK[V_CORROBORATED]
        if m.lifecycle == L_REJECTED:
            target = "unpublished"
        elif m.retention == R_SUPERSEDED:
            target = "retired"
        elif verified and m.retention in (R_RETAINED, R_UNMANAGED):
            target = "published"
        else:
            target = "unpublished"
        if target == "published":
            published += 1
        if target != m.publication:
            events.append(Event({"published": "model_published", "retired": "model_retired"}.get(target, "model_unpublished"), "model", key, ts,
                                m.publication, target))
            m.publication = target
            if target == "published":
                m.published_at = m.published_at or ts
    return published


def refresh(store, sources: list, *, trigger: str = "scheduled", now: Optional[datetime] = None, force: bool = False,
            time_budget_seconds: float = 45.0, only: Optional[set] = None) -> RefreshReport:
    now = now or datetime.now(timezone.utc)
    started = time.monotonic()
    ts = iso(now)
    run_id = uuid.uuid4().hex[:16]
    report = RefreshReport(run_id=run_id, trigger=trigger, started_at=ts)

    with store.try_lock() as acquired:
        if not acquired:
            report.status, report.finished_at = "skipped", iso(datetime.now(timezone.utc))
            report.notes.append("another refresh is already running")
            return report
        state = store.load()
        loaded_version = state.version
        sync_developers(state)
        base = copy.deepcopy(state)
        events: list = []
        observations: list = []
        results: dict = {}
        any_ok = any_fail = False

        for src in sources:
            if only and src.source_id not in only:
                continue
            sst = state.sources.setdefault(src.source_id, SourceState(src.source_id, src.kind, True, src.default_interval_minutes))
            if not force and not is_due(sst, sst.refresh_interval_minutes, now):
                report.sources.append({"source": src.source_id, "status": "not_due"})
                continue
            if time.monotonic() - started > time_budget_seconds:
                report.sources.append({"source": src.source_id, "status": "deferred", "reason": "time budget"})
                continue
            sst.last_attempt_at = ts
            try:
                res = src.fetch(sst, state.developers, now)
            except FetchError as exc:
                sst.consecutive_failures += 1
                status = {"rate_limited": "rate_limited", "timeout": "timed_out"}.get(exc.kind, "failed")
                sst.status, sst.last_error = status, exc.kind
                any_fail = True
                events.append(Event("source_failed", "source", src.source_id, ts, reason=exc.kind, run_id=run_id))
                report.sources.append({"source": src.source_id, "status": status, "error": exc.kind})
                continue
            except Exception as exc:                       # noqa: BLE001 - adapters process untrusted data; never let one abort the run
                logger.warning("source %s crashed: %s", src.source_id, type(exc).__name__)
                sst.consecutive_failures += 1
                sst.status, sst.last_error = "failed", "adapter_error"
                any_fail = True
                events.append(Event("source_failed", "source", src.source_id, ts, reason="adapter_error", run_id=run_id))
                report.sources.append({"source": src.source_id, "status": "failed", "error": "adapter_error"})
                continue
            any_ok = True
            prev_count = sst.last_count
            if prev_count and res.raw_count < prev_count * COMPLETENESS_FLOOR and not res.not_modified:
                res.complete = False                        # implausibly small: never trust it to prove absence
                res.notes.append(f"response shrank from {prev_count} to {res.raw_count}; treated as partial")
            sst.consecutive_failures, sst.last_error = 0, None
            sst.last_success_at = ts
            sst.etag = res.etag or sst.etag
            sst.cursor = res.cursor if res.cursor is not None else sst.cursor
            sst.status = "ok" if res.complete or res.not_modified else "partial"
            if res.raw_count and not res.not_modified and (res.complete or not prev_count):
                sst.last_count = res.raw_count
            for ns, n in res.unregistered.items():
                report.unregistered_developers[ns] = report.unregistered_developers.get(ns, 0) + n
            results[src.source_id] = (src, res)
            observations += res.observations
            report.sources.append({"source": src.source_id, "status": sst.status, "observed": len(res.observations), "raw": res.raw_count,
                                   "rejected": res.rejected, "not_modified": res.not_modified, "notes": res.notes[:5]})

        # ── merge + derive, all against the in-memory copy; nothing is persisted until the end ──────────
        merge_events = merge_mod.merge_observations(state, observations, now, run_id)
        observed = {f"{k}|{o.offering_provider}|{o.offering_model_id}" for k, o in _keyed(state, observations)}
        for src, res in results.values():
            _count_absences(state, src, res, observed, ts, merge_events, run_id)
        for src, res in results.values():
            if res.leads:
                merge_events += announcements.detect(res.leads, state, ts, run_id)
            if res.evidence:
                merge_events += announcements.corroborate(res.evidence, state, ts, run_id)
        merge_events += merge_mod.derive_availability(state, now)
        merge_events += retention_mod.apply_retention(state, now)
        prev_published = sum(1 for m in base.models.values() if m.publication == "published")
        new_published = _publication(state, ts, merge_events)
        for e in merge_events:
            e.run_id = e.run_id or run_id

        problems = retention_mod.assert_invariants(state)
        if prev_published >= 8 and new_published < prev_published * (1 - MASS_REMOVAL_LIMIT):
            problems.append(f"publication would drop {prev_published}->{new_published} models (>25%)")
        if problems:
            # keep only source health from this run; discard every catalogue change
            for sid, sst in state.sources.items():
                base.sources[sid] = sst
            state, merge_events = base, []
            report.status = "aborted"
            report.notes += problems
            events.append(Event("publication_aborted", "catalog", "catalog", ts, reason="; ".join(problems)[:500], run_id=run_id))
        else:
            events += merge_events

        catalog_changed = bool(merge_events)
        if catalog_changed:
            state.version = loaded_version + 1
            state.published_at = ts
        report.counts = {"events": len(events), "published": new_published if report.status != "aborted" else prev_published,
                         "catalog_changed": catalog_changed}
        if report.status != "aborted":
            report.status = "failed" if (any_fail and not any_ok) else ("partial" if any_fail else "ok")
        report.finished_at = iso(datetime.now(timezone.utc))
        if not store.commit(state, events, report, expected_version=loaded_version, bump=catalog_changed):
            report.status = "conflict"
            report.notes.append("catalogue changed concurrently; nothing was written, retry on the next run")
            return report
        report.published, report.version = catalog_changed and report.status != "aborted", state.version
        return report


def _keyed(state: CatalogState, observations: list):
    from app.services.catalog.versions import classify
    for ob in observations:
        dev = state.developers.get(ob.developer or "")
        cls = classify(ob.offering_model_id.split("/", 1)[-1], ob.name, ob.developer, family_includes=tuple(dev.family_includes) if dev else (),
                       out_modalities=tuple(ob.output_modalities))
        yield f"{ob.developer or cls.developer or 'unknown'}:{cls.canonical_slug}", ob
