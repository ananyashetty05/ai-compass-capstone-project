"""Observations -> canonical models + offerings, with field-level provenance.

A canonical model is the underlying model (``developer:canonical_slug``); an offering is one
provider's way of accessing it, with its own price and URLs. Higher-authority sources win each
field; disagreements are recorded, never silently averaged. Unknown stays unknown.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.services.catalog.state import (AUTH_RANK, OFFICIAL_AUTHORITIES, CatalogState, Event, ModelRecord, Observation, OfferingRecord,
                                         V_CORROBORATED, V_DETECTED, V_OFFICIAL, V_RANK, iso, parse_iso)
from app.services.catalog.versions import classify

AGGREGATOR_PERSIST = timedelta(hours=24)
_SCALARS = ("context_window", "max_output_tokens", "open_weights", "license", "parameter_count", "description", "benchmarks")


def _tail(model_id: str) -> str:
    return model_id.split("/", 1)[-1]


def fingerprint(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _best(obs: list, attr: str):
    """Value from the highest-authority observation that has one, plus the observation and any conflicting values."""
    have = [o for o in obs if getattr(o, attr) not in (None, "", ())]
    if not have:
        return None, None, []
    have.sort(key=lambda o: AUTH_RANK.get(o.authority, 9))
    win = have[0]
    other = sorted({str(getattr(o, attr)) for o in have[1:] if getattr(o, attr) != getattr(win, attr) and attr != "description"})
    return getattr(win, attr), win, other


def merge_observations(state: CatalogState, observations: Iterable[Observation], now: datetime, run_id: Optional[str] = None) -> list:
    """Upserts models/offerings in ``state`` in place. Returns events. Idempotent for identical input."""
    events: list = []
    ts = iso(now)
    groups: dict = {}
    for ob in observations:
        dev_rec = state.developers.get(ob.developer or "")
        cls = classify(_tail(ob.offering_model_id), ob.name, ob.developer, family_includes=tuple(dev_rec.family_includes) if dev_rec else (),
                       out_modalities=tuple(ob.output_modalities))
        dev = ob.developer or cls.developer or "unknown"
        key = f"{dev}:{cls.canonical_slug}"
        groups.setdefault(key, (cls, dev, []))[2].append(ob)

    for key, (cls, dev, obs) in groups.items():
        # ── offerings (always upserted; price/URLs belong to the offering, never the model) ─────────
        for ob in obs:
            okey = f"{key}|{ob.offering_provider}|{ob.offering_model_id}"
            off = state.offerings.get(okey)
            new_vals = dict(pricing=ob.pricing, urls=[dict(u) for u in ob.urls], context_window=ob.context_window, max_output_tokens=ob.max_output_tokens,
                            expires_at=ob.expires_at, deprecated=ob.deprecated)
            if off is None:
                state.offerings[okey] = OfferingRecord(offering_key=okey, canonical_key=key, provider=ob.offering_provider, offering_model_id=ob.offering_model_id,
                                                       source_id=ob.source_id, authority=ob.authority, first_seen_at=ts, curated=ob.curated, **new_vals)
                events.append(Event("offering_discovered", "offering", okey, ts, to_state="listed", run_id=run_id))
            else:
                changed = any(getattr(off, k) != v for k, v in new_vals.items())
                if not off.listed:
                    events.append(Event("offering_relisted", "offering", okey, ts, "unlisted", "listed", run_id=run_id))
                off.listed, off.consecutive_missing = True, 0
                if changed:
                    for k, v in new_vals.items():
                        setattr(off, k, v)
                    events.append(Event("offering_changed", "offering", okey, ts, run_id=run_id))
                if ob.curated and not off.curated:
                    off.curated = ob.curated

        # ── canonical model ─────────────────────────────────────────────────────────────────────
        rec = state.models.get(key)
        is_new = rec is None
        if is_new:
            rec = ModelRecord(canonical_key=key, developer=dev if dev != "unknown" else None, name=obs[0].name, family=cls.family, track=cls.track,
                              lineage_key=cls.lineage_key, first_seen_at=ts)
            state.models[key] = rec
        before = fingerprint({k: v for k, v in rec.__dict__.items() if k not in ("last_changed_at", "published_at", "superseded_at")})

        rec.family, rec.track, rec.lineage_key = cls.family, cls.track, cls.lineage_key
        rec.generation_key, rec.generation_kind, rec.generation_label = cls.generation_key, cls.kind, cls.label
        rec.generation_sort = list(cls.sort_key)
        rec.variants, rec.size, rec.stage = list(cls.variants), cls.size, cls.stage
        rec.classification_confidence = cls.confidence
        best_name = sorted(obs, key=lambda o: AUTH_RANK.get(o.authority, 9))[0]
        rec.name = best_name.name
        prov, conflicts = dict(rec.provenance), []
        prov["name"] = {"source": best_name.source_id, "authority": best_name.authority}
        for attr in _SCALARS:
            val, win, other = _best(obs, attr)
            if win is not None:
                setattr(rec, attr, val)
                prov[attr] = {"source": win.source_id, "authority": win.authority}
                if other:
                    conflicts.append({"field": attr, "chosen": str(val), "others": other[:4]})
        for attr, store in (("capabilities", "capabilities"), ("input_modalities", "input_modalities"), ("output_modalities", "output_modalities")):
            vals = sorted({v for o in obs for v in getattr(o, attr)})
            if vals:
                setattr(rec, store, vals)
                prov[attr] = {"source": ",".join(sorted({o.source_id for o in obs if getattr(o, attr)})), "authority": "merged"}
        dated = sorted((o for o in obs if o.released_at), key=lambda o: (AUTH_RANK.get(o.authority, 9), o.released_at))
        if dated:
            rec.released_at, rec.released_at_kind = dated[0].released_at, dated[0].released_at_kind
            prov["released_at"] = {"source": dated[0].source_id, "authority": dated[0].authority}
        tax = next((o.taxonomy for o in obs if o.taxonomy), None)
        if tax:
            rec.taxonomy = tax
        cur = next((o.curated for o in obs if o.curated), None)
        if cur:
            rec.curated = cur
        rec.sources = sorted(set(rec.sources) | {o.source_id for o in obs})
        rec.provenance, rec.conflicts = prov, conflicts

        # ── verification: never downgrades; corroboration needs independent evidence ───────────────
        level = V_DETECTED
        sources = {o.source_id for o in obs} | set(rec.sources)
        if any(o.authority in OFFICIAL_AUTHORITIES for o in obs):
            level = V_OFFICIAL
        else:
            known_dev = dev in state.developers
            first = parse_iso(rec.first_seen_at) if rec.first_seen_at else now
            if len(sources) >= 2 or (known_dev and now - first >= AGGREGATOR_PERSIST):
                level = V_CORROBORATED
        if V_RANK[level] > V_RANK.get(rec.verification, 0):
            events.append(Event("verification_changed", "model", key, ts, rec.verification, level, run_id=run_id))
            rec.verification = level

        after = fingerprint({k: v for k, v in rec.__dict__.items() if k not in ("last_changed_at", "published_at", "superseded_at")})
        if is_new:
            rec.last_changed_at = ts
            events.append(Event("model_discovered", "model", key, ts, to_state=rec.verification, reason=best_name.source_id, run_id=run_id))
        elif before != after:
            rec.last_changed_at = ts
            events.append(Event("model_metadata_changed", "model", key, ts, run_id=run_id))
    return events


def derive_availability(state: CatalogState, now: datetime) -> list:
    """Model availability/lifecycle from its offerings. Missing != discontinued: only explicit expiry or deprecation retires."""
    events: list = []
    ts, now_iso = iso(now), iso(now)
    by_model: dict = {}
    for off in state.offerings.values():
        by_model.setdefault(off.canonical_key, []).append(off)
    for key, rec in state.models.items():
        offs = by_model.get(key, [])
        live = [o for o in offs if o.listed and not (o.expires_at and o.expires_at < now_iso)]
        if live and all(o.deprecated for o in live):
            avail = "deprecated"
        elif live:
            avail = "public"
        elif offs and all(o.expires_at and o.expires_at < now_iso for o in offs):
            avail = "discontinued"
        elif offs:
            avail = "unavailable"
        else:
            avail = "unknown"
        if avail != rec.availability:
            events.append(Event("availability_changed", "model", key, ts, rec.availability, avail))
            rec.availability = avail
    return events
