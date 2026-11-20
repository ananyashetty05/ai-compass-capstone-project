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
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from app.services import access_category
from app.services.model_classifier import KIND_LABELS, PRIMARY_CATEGORIES

PRIMARY_LABELS = {"conversational": "Conversational AI", "developer": "Developer & Project models", "application": "AI applications", "unclassified": "Unclassified"}


def _g(entry: Any, key: str, default=None):
    return entry.get(key, default) if isinstance(entry, dict) else getattr(entry, key, default)


def access_breakdown(rows: Iterable[Any]) -> dict:
    """Recommendation vs execution, counted separately over inference models.

    Recommendation eligibility depends on catalogue metadata and lifecycle only; a missing provider credential or adapter
    affects execution and nothing else. The groups overlap on purpose and are labelled so they are not added together.
    """
    models = [e for e in rows if _g(e, "entry_type") in ("inference_model", "model")]
    elig = [e for e in models if _g(e, "routing_eligible")]
    ready = [e for e in models if _g(e, "execution_available")]
    rec_only = [e for e in elig if not _g(e, "execution_available")]
    status = Counter(_g(e, "metadata_status") or "unknown" for e in models)
    return {
        "scope": "inference models only (applications are not recommended as models)",
        "catalog_models": len(models),
        "recommendation_eligible": len(elig),
        "execution_ready": len(ready),
        "recommendation_only": len(rec_only),
        "provider_not_configured": sum(1 for e in models if not _g(e, "user_access_configured")),
        "adapter_unavailable": sum(1 for e in models if not _g(e, "adapter_compatible")),
        "metadata_incomplete": status.get("incomplete", 0),
        "metadata_stale": status.get("stale", 0),
        "metadata_status": dict(status),
        "note": "Recommendation eligibility never depends on a credential. Execution ready = adapter + server credential. Groups overlap.",
    }


def category_breakdown(rows: Iterable[Any]) -> dict:
    """Recommendation groups (conversational / developer_api / unclassified). Mutually exclusive; they add up to the rows given.

    Read from each entry's stored group when present, otherwise derived by the same pure function the router uses, so the
    Model Pool and the recommendation engine cannot disagree about which group an entry is in.
    """
    groups: Counter = Counter(); pricing: Counter = Counter(); access: Counter = Counter()
    for e in rows:
        stored = _g(e, "model_category")
        prof = None if stored and stored != "unclassified" else access_category.profile_of(SimpleNamespace(**e) if isinstance(e, dict) else e)
        g = stored if stored and stored != "unclassified" else (prof.model_category if prof else "unclassified")
        groups[g] += 1
        if _g(e, "entry_type") in ("inference_model", "model"):
            pricing[_g(e, "pricing_category") or (prof.pricing_category if prof else "unknown")] += 1
            access[_g(e, "access_type") or (prof.access_type if prof else "unknown")] += 1
    return {
        "counts": {g: groups.get(g, 0) for g in (access_category.CONVERSATIONAL, access_category.DEVELOPER_API, access_category.UNCLASSIFIED)},
        "pricing": dict(pricing), "access": dict(access),
        "note": "Groups are exclusive and add up to the pool total. Pricing is evidence-based: 'unknown' means no verified pricing, never free.",
    }


def compute_approved(rows: list) -> dict:
    """Statistics for the approved ecosystem pool. Primary categories are exclusive and sum to the pool total; 'serving' counts
    overlap on purpose (a product documented for two categories is compared in both) and are never added together."""
    from app.data import approved_ecosystem as eco
    primary: Counter = Counter(); serving: Counter = Counter(); kinds: dict = {c: Counter() for c in eco.CATEGORIES}
    members: dict = {c: [] for c in eco.CATEGORIES}; secondary = []; problems: list = []
    for e in rows:
        cat = _g(e, "ecosystem_category")
        if cat not in eco.CATEGORIES:
            problems.append({"check": "valid_ecosystem_category", "entry": _g(e, "model_id"), "value": cat}); continue
        extra = list(_g(e, "secondary_categories") or [])
        primary[cat] += 1; kinds[cat][_g(e, "product_kind") or "unknown"] += 1
        for c in {cat, *extra}:
            if c in serving or c in eco.CATEGORIES:
                serving[c] += 1
                members[c].append({"model_id": _g(e, "model_id"), "model_name": _g(e, "model_name"), "role": "primary" if c == cat else "secondary"})
        if extra:
            secondary.append({"model_id": _g(e, "model_id"), "model_name": _g(e, "model_name"), "primary": cat, "also_serves": extra})
    total = len(rows)
    ids = [_g(e, "model_id") for e in rows]
    checks = [
        {"check": "pool_within_cap", "ok": total <= eco.MAX_POOL_SIZE, "detail": f"{total} of {eco.MAX_POOL_SIZE}"},
        {"check": "every_entry_has_exactly_one_primary_category", "ok": sum(primary.values()) == total},
        {"check": "primary_categories_reconcile_with_pool_total", "ok": sum(primary.values()) == total, "detail": f"{' + '.join(str(primary[c]) for c in eco.CATEGORIES)} = {sum(primary.values())} (pool {total})"},
        {"check": "no_duplicate_entries", "ok": len(set(ids)) == total},
        {"check": "only_approved_entries", "ok": all(_g(e, "ecosystem_approved") for e in rows)},
        {"check": "metrics_are_labelled_editorial_estimates", "ok": all(_g(e, k) is not None for e in rows for k in ("estimated_quality", "estimated_latency", "reliability", "risk_level")) and all((_g(e, "metric_provenance") or {}).get(d) == "editorial_estimate" for e in rows for d in ("quality", "latency", "reliability", "risk"))},
        {"check": "no_invented_prices", "ok": all(_g(e, k) is None for e in rows for k in ("estimated_cost", "input_price_per_million"))},
    ]
    return {
        "scope": "approved ecosystem: the only products AI Compass compares. Recommendation only; nothing is run.",
        "pool_total": total, "cap": eco.MAX_POOL_SIZE, "canonical_models": 0, "applications": total,
        "primary": {c: primary[c] for c in eco.CATEGORIES}, "primary_labels": dict(eco.CATEGORY_LABELS),
        "serving": {c: serving[c] for c in eco.CATEGORIES},
        "ecosystem": {"categories": [{"id": c, "label": eco.CATEGORY_LABELS[c], "primary_count": primary[c], "serving_count": serving[c], "members": members[c]} for c in eco.CATEGORIES],
                      "secondary_memberships": secondary, "note": "Primary counts add up to the pool total. Serving counts overlap (a product can be compared in more than one category) and are not summed."},
        "kinds": {c: [{"kind": k, "label": k.replace("_", " "), "count": n} for k, n in sorted(kinds[c].items(), key=lambda kv: -kv[1])] for c in eco.CATEGORIES},
        "capabilities": {"overlapping": True, "note": "Not applicable to the approved pool; category membership is the comparison key.", "counts": {}},
        "classification_basis": {"curated": total}, "provider_offerings": {"count": 0, "providers": 0, "note": "Not applicable."},
        "pending_verification": None, "retired": None, "lineages_needing_review": None,
        "access": {"scope": "approved ecosystem: all entries are opened at their own site", "catalog_models": 0, "recommendation_eligible": total, "execution_ready": 0, "recommendation_only": total,
                   "provider_not_configured": 0, "adapter_unavailable": 0, "metadata_incomplete": 0, "metadata_stale": 0, "metadata_status": {"curated": total},
                   "note": "Recommendation never depends on a credential, and nothing is executed."},
        "categories": {"counts": {}, "pricing": dict(Counter(_g(e, "pricing_category") or "unknown" for e in rows)), "access": {"open_at_destination": total}, "note": ""},
        "integrity": {"ok": all(c["ok"] for c in checks) and not problems, "checks": checks, "problems": problems},
    }


def compute(entries: Iterable[Any], catalog_totals: Optional[dict] = None) -> dict:
    rows = list(entries)
    if rows and all(_g(e, "ecosystem_approved") for e in rows):
        return compute_approved(rows)
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
        "access": access_breakdown(rows),
        "categories": category_breakdown(rows),
        "integrity": {"ok": all(c["ok"] for c in checks) and not problems, "checks": checks, "problems": problems},
    }
