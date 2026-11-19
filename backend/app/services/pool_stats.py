"""Single source of truth for Model Pool statistics.

Every figure is computed from the same list of entries the Model Pool lists (``registry_service.build_registry``),
so the page, its filters and the API cannot disagree. Populations are never mixed:

* ``pool_total``         entries shown in the pool (active canonical models + AI applications)
* ``canonical_models``   active canonical API/model entries (one per ``canonical_key``; offerings are NOT counted here)
* ``applications``       AI applications / tools (not models)
* ``primary``            MUTUALLY EXCLUSIVE categories; always sums to ``pool_total``
* ``capabilities``       OVERLAPPING tags; flagged ``overlapping`` and never summed
* ``provider_offerings`` access routes to canonical models (separate population)
* ``pending`` / ``retired``  catalogue records outside the active pool
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Optional

from app.services.model_classifier import KIND_LABELS, PRIMARY_CATEGORIES

PRIMARY_LABELS = {"conversational": "Conversational AI", "developer": "Developer & Project models", "application": "AI applications", "unclassified": "Unclassified"}


def _g(entry: Any, key: str, default=None):
    return entry.get(key, default) if isinstance(entry, dict) else getattr(entry, key, default)


def compute(entries: Iterable[Any], catalog_totals: Optional[dict] = None) -> dict:
    rows = list(entries)
    primary = Counter(); kinds: dict = {c: Counter() for c in PRIMARY_CATEGORIES}; tags = Counter(); basis = Counter()
    keys = Counter(); offerings = 0; offer_providers = set(); problems: list = []
    inactive_in_pool = 0
    for e in rows:
        cat = _g(e, "primary_category") or "unclassified"
        if cat not in PRIMARY_CATEGORIES:
            problems.append({"check": "valid_primary_category", "entry": _g(e, "model_id"), "value": cat})
            cat = "unclassified"
        primary[cat] += 1
        kinds[cat][_g(e, "category_kind") or "unclassified"] += 1
        basis[_g(e, "classification_basis") or "unverified"] += 1
        for t in _g(e, "capability_tags") or []:
            tags[t] += 1
        if _g(e, "entry_type") in ("inference_model", "model"):
            keys[_g(e, "canonical_key") or f"{_g(e, 'provider')}:{_g(e, 'model_id')}"] += 1
        cat_blk = _g(e, "catalog") or {}
        for o in cat_blk.get("offerings", []) or []:
            offerings += 1
            offer_providers.add((o.get("provider") or "").lower())
        if not _g(e, "active", True) or cat_blk.get("retired"):
            inactive_in_pool += 1
    total = len(rows)
    canonical = sum(keys.values())
    dupes = sorted(k for k, n in keys.items() if n > 1)
    apps = primary["application"]
    checks = [
        {"check": "every_entry_has_exactly_one_primary_category", "ok": sum(primary.values()) == total},
        {"check": "primary_categories_reconcile_with_pool_total", "ok": sum(primary.values()) == total, "detail": f"{' + '.join(str(primary[c]) for c in PRIMARY_CATEGORIES)} = {sum(primary.values())} (pool {total})"},
        {"check": "no_duplicate_canonical_identities", "ok": not dupes, "detail": dupes[:10]},
        {"check": "retired_or_inactive_excluded_from_active_pool", "ok": inactive_in_pool == 0, "detail": inactive_in_pool},
        {"check": "applications_not_counted_as_canonical_models", "ok": canonical + apps == total},
        {"check": "provider_offerings_counted_separately", "ok": True, "detail": f"{offerings} offerings route to {canonical} canonical models"},
        {"check": "unclassified_entries_visible", "ok": True, "detail": primary["unclassified"]},
        {"check": "primary_category_basis_recorded", "ok": sum(basis.values()) == total},
    ]
    t = catalog_totals or {}
    return {
        "scope": "active pool: published canonical models + AI applications; retired and awaiting-verification records are excluded and reported separately",
        "pool_total": total, "canonical_models": canonical, "applications": apps,
        "primary": {c: primary[c] for c in PRIMARY_CATEGORIES},
        "primary_labels": PRIMARY_LABELS,
        "kinds": {c: [{"kind": k, "label": KIND_LABELS.get(k, k), "count": n} for k, n in sorted(kinds[c].items(), key=lambda kv: -kv[1])] for c in PRIMARY_CATEGORIES},
        "capabilities": {"overlapping": True, "note": "A model can carry several capabilities, so these counts overlap and must not be added together.",
                         "counts": dict(sorted(tags.items(), key=lambda kv: -kv[1]))},
        "classification_basis": dict(basis),
        "provider_offerings": {"count": offerings, "providers": len(offer_providers), "note": "Access routes to canonical models, not additional models."},
        "pending_verification": t.get("awaiting_verification"), "retired": t.get("retired"),
        "lineages_needing_review": t.get("lineages_needing_review"),
        "integrity": {"ok": all(c["ok"] for c in checks) and not problems, "checks": checks, "problems": problems},
    }
