"""Autonomous model catalogue API. Reads never trigger discovery; refresh is cron- or admin-initiated only."""
from __future__ import annotations

import hmac
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.logging import get_logger
from app.api.routes.models import require_registry_admin
from app.services import registry_service
from app.services.catalog import engine, registry, sources as src_mod
from app.services.catalog.state import DeveloperRecord, iso
from app.services.catalog.store import MemoryStore, StoreUnavailable

router = APIRouter()
logger = get_logger(__name__)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{1,39}$")
_DOMAIN = re.compile(r"^(?=.{4,100}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


@router.get("/catalog/summary")
def catalog_summary():
    return registry.summary()


@router.get("/catalog/families")
def catalog_families():
    return registry.families()


@router.get("/catalog/developers")
def catalog_developers():
    st = registry.state()
    return [{"slug": d.slug, "name": d.name, "homepage": d.homepage, "enabled": d.enabled,
             "published_models": sum(1 for m in st.models.values() if m.developer == d.slug and m.publication == "published")}
            for d in sorted(st.developers.values(), key=lambda d: d.name.lower())]


@router.get("/catalog/events")
def catalog_events(limit: int = Query(50, ge=1, le=200), event_type: Optional[str] = None):
    if registry.origin() != "store":
        return []
    return registry.get_store().recent_events(limit=limit, event_types={event_type} if event_type else None)


@router.get("/catalog/runs")
def catalog_runs(limit: int = Query(20, ge=1, le=100)):
    if registry.origin() != "store":
        return []
    return registry.get_store().recent_runs(limit=limit)


@router.get("/catalog/models/history")
def catalog_model_history(key: str = Query(..., min_length=3, max_length=200), limit: int = Query(50, ge=1, le=200)):
    if registry.state().models.get(key) is None:
        raise HTTPException(404, "Unknown catalogue model.")
    if registry.origin() != "store":
        return []
    return registry.get_store().model_history(key, limit)


class DeveloperIn(BaseModel):
    slug: str
    name: str = Field(min_length=2, max_length=80)
    homepage: Optional[str] = None
    aliases: list[str] = Field(default_factory=list, max_length=10)
    openrouter_prefixes: list[str] = Field(default_factory=list, max_length=10)
    huggingface_orgs: list[str] = Field(default_factory=list, max_length=10)
    official_domains: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG.match(v):
            raise ValueError("slug must be 2-40 lowercase letters, digits or hyphens")
        return v

    @field_validator("official_domains")
    @classmethod
    def _domains(cls, v: list[str]) -> list[str]:
        for d in v:
            if not _DOMAIN.match(d.lower()):
                raise ValueError(f"invalid domain: {d!r}")
        return [d.lower() for d in v]

    @field_validator("openrouter_prefixes", "huggingface_orgs", "aliases")
    @classmethod
    def _tokens(cls, v: list[str]) -> list[str]:
        for t in v:
            if not re.fullmatch(r"[A-Za-z0-9._\-]{1,60}", t):
                raise ValueError(f"invalid identifier: {t!r}")
        return v

    @field_validator("homepage")
    @classmethod
    def _home(cls, v: Optional[str]) -> Optional[str]:
        if v and (urlsplit(v).scheme != "https" or not urlsplit(v).hostname):
            raise ValueError("homepage must be an https URL")
        return v


def _require_persistence() -> None:
    if not registry.persistence_enabled():
        raise HTTPException(503, "Catalogue persistence is not enabled on this deployment (apply the approved migration and set CATALOG_PERSISTENCE_ENABLED).")


@router.post("/catalog/developers", status_code=201)
def register_developer(body: DeveloperIn, _: str = Depends(require_registry_admin)):
    """Add a model developer without touching engine code. Takes effect on the next refresh."""
    _require_persistence()
    store = registry.get_store()
    with store.try_lock() as ok:
        if not ok:
            raise HTTPException(409, "A refresh is running; retry shortly.")
        st = store.load()
        if body.slug in st.developers:
            raise HTTPException(409, "A developer with this slug already exists.")
        st.developers[body.slug] = DeveloperRecord(**body.model_dump())
        report = engine.RefreshReport(run_id=f"dev-{body.slug}", trigger="register_developer", started_at=iso(datetime.now(timezone.utc)), status="ok")
        report.finished_at = report.started_at
        if not store.commit(st, [], report, expected_version=st.version, bump=False):
            raise HTTPException(409, "Catalogue changed concurrently; retry.")
    registry.invalidate()
    return {"slug": body.slug, "status": "registered"}


def _run_refresh(trigger: str, force: bool, only: Optional[set] = None) -> dict:
    _require_persistence()
    try:
        report = engine.refresh(registry.get_store(), src_mod.default_sources(), trigger=trigger, force=force, only=only,
                                time_budget_seconds=settings.CATALOG_REFRESH_TIME_BUDGET_SECONDS)
    except StoreUnavailable as exc:
        raise HTTPException(503, "Catalogue store unavailable.") from exc
    except Exception:
        logger.exception("catalogue refresh failed")
        raise HTTPException(500, "Catalogue refresh failed; the published catalogue was not changed.")
    registry.invalidate()
    registry_service.invalidate_cache()
    return report.__dict__


def _dry_run(force: bool, only: Optional[set]) -> dict:
    """Real network fetch + full pipeline against a COPY of the current catalogue. Nothing is persisted or published."""
    import copy
    before = registry.state()
    store = MemoryStore(copy.deepcopy(before))
    report = engine.refresh(store, [s for s in src_mod.default_sources() if s.kind != "documentation_snapshot"], trigger="dry_run", force=force, only=only,
                            time_budget_seconds=settings.CATALOG_REFRESH_TIME_BUDGET_SECONDS)
    return {"report": report.__dict__, "diff": registry.diff_summary(before, store.load())}


@router.post("/catalog/refresh")
def manual_refresh(force: bool = Query(True), source: Optional[str] = Query(None, max_length=40), dry_run: bool = Query(False),
                   _: str = Depends(require_registry_admin)):
    if dry_run:
        return _dry_run(force, {source} if source else None)
    return _run_refresh("manual", force, {source} if source else None)


@router.get("/catalog/cron")
def cron_refresh(authorization: Optional[str] = Header(default=None), force: bool = Query(False)):
    """Invoked by Vercel Cron (GET + ``Authorization: Bearer $CRON_SECRET``). Runs only sources that are due, unless ``force=true`` (same effect as a manual refresh)."""
    secret = settings.CRON_SECRET
    if not secret:
        raise HTTPException(503, "Cron is not configured on this deployment.")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise HTTPException(401, "Invalid cron credential.")
    return _run_refresh("cron", force=force)
