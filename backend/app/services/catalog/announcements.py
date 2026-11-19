"""Release announcements as DISCOVERY SIGNALS.

An announcement is never proof that a model exists or is callable, so nothing here creates, publishes or retires a model. A lead is only
recorded as an event ("announcement_detected") pointing at the developer's own post, labelled published / awaiting_verification / not_yet_listed
according to what the catalogue already holds for that generation. The catalogue changes only through verified sources (see merge/retention).

Parsing is deliberately a small, bounded regex reader rather than an XML parser: feeds are untrusted input, and this avoids entity-expansion
and external-entity attacks entirely.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from app.services.catalog.state import Event, V_CORROBORATED, V_RANK, iso

MAX_ITEMS_PER_FEED = 60
FIRST_RUN_WINDOW = timedelta(days=45)
_ITEM = re.compile(r"<item\b[^>]*>(.*?)</item>", re.S | re.I)
_TAG = {k: re.compile(rf"<{k}\b[^>]*>(.*?)</{k}>", re.S | re.I) for k in ("title", "link", "pubDate", "guid")}
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_VERSIONED: dict = {}


def _family_rx(family: str):
    rx = _VERSIONED.get(family)
    if rx is None:
        body = "[ -]?".join(re.escape(p) for p in family.split("-"))
        rx = _VERSIONED[family] = re.compile(rf"(?<![a-z0-9]){body}[\s\-]*v?(\d+(?:\.\d+)*)", re.I)
    return rx


def _text(raw: Optional[str], limit: int = 200) -> Optional[str]:
    if raw is None:
        return None
    m = _CDATA.search(raw)
    s = m.group(1) if m else raw
    s = re.sub(r"<[^>]+>", " ", html.unescape(s))
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


def parse_feed(text: str, *, since: Optional[datetime], now: datetime) -> list:
    """Items newer than ``since`` (or inside the first-run window), newest first, bounded."""
    floor = since or (now - FIRST_RUN_WINDOW)
    out = []
    for m in _ITEM.finditer(text[:6_000_000]):
        body = m.group(1)
        fields = {k: _text((rx.search(body) or [None, None])[1] if rx.search(body) else None, 400) for k, rx in _TAG.items()}
        title, link = fields["title"], fields["link"] or fields["guid"]
        if not title or not link:
            continue
        try:
            published = parsedate_to_datetime(fields["pubDate"]) if fields["pubDate"] else None
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        if published is None or published <= floor or published > now + timedelta(days=1):
            continue
        out.append({"title": title[:200], "url": link[:500], "published_at": iso(published)})
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out[:MAX_ITEMS_PER_FEED]


def _norm_version(v: str) -> str:
    parts = [int(p) for p in v.split(".") if p.isdigit()]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return ".".join(str(p) for p in parts)


def detect(leads: list, state, ts: str, run_id: Optional[str] = None) -> list:
    """Keep only announcements that mention a model family the catalogue already tracks for that developer, followed by a version."""
    by_dev: dict = {}
    for m in state.models.values():
        if not m.developer or len(m.family) < 2:
            continue
        fam = by_dev.setdefault(m.developer, {}).setdefault(m.family, {"published": set(), "detected": set()})
        if m.generation_label:
            fam["published" if m.publication == "published" else "detected"].add(_norm_version(str(m.generation_label)))
    events, seen = [], set()
    for lead in leads:
        if lead["url"] in seen:
            continue
        title = lead["title"].lower()
        for family, seen_versions in by_dev.get(lead["developer"], {}).items():
            hit = _family_rx(family).search(title)
            if hit:
                version = _norm_version(hit.group(1))
                seen.add(lead["url"])
                events.append(Event("announcement_detected", "announcement", lead["url"], lead["published_at"],
                                    from_state=f"{family} {version}", to_state=("published" if version in seen_versions["published"] else "awaiting_verification" if version in seen_versions["detected"] else "not_yet_listed"),
                                    reason=lead["title"], run_id=run_id))
                break
    return events


_NOISE = {"preview", "exp", "experimental", "latest", "instruct", "chat", "free", "batch", "it", "hf", "text", "base"}


def _distinguishing(slug: str, family: str) -> set:
    fam = set(family.split("-"))
    return {t for t in slug.split("-") if t and t not in fam and t not in _NOISE and not re.fullmatch(r"\d+(?:\.\d+)*", t) and not re.fullmatch(r"\d{4,8}", t)}


def corroborate(evidence: list, state, ts: str, run_id: Optional[str] = None) -> list:
    """An official announcement naming a model is an independent second source for a model another source already lists.

    A post vouches for a model only when it names the same family AND version AND every distinguishing token of that model's own name
    (so "Gemini 4 Hydrogen" cannot vouch for "Gemini 4 Neon", and "GPT-6.2 Astra and Sol" cannot vouch for "GPT-6.2 Astra Pro").
    It never creates a model, and it never lowers a verification level.
    """
    events: list = []
    for lead in evidence:
        title = lead["title"].lower()
        words = set(re.findall(r"[a-z0-9]+", title))
        for rec in state.models.values():
            if rec.developer != lead["developer"] or not rec.generation_label or len(rec.family) < 2 or "announcements" in rec.sources:
                continue
            hit = _family_rx(rec.family).search(title)
            if not hit or _norm_version(hit.group(1)) != _norm_version(str(rec.generation_label)):
                continue
            slug = rec.canonical_key.split(":", 1)[-1]
            distinct = _distinguishing(slug, rec.family)
            if not distinct <= words:
                continue
            if not rec.sources or set(rec.sources) <= {"announcements"}:
                continue                                           # needs a real catalogue listing from another source first
            rec.sources = sorted(set(rec.sources) | {"announcements"})
            rec.provenance = {**rec.provenance, "announcement": {"source": "announcements", "authority": "developer_announcement", "url": lead["url"], "title": lead["title"]}}
            if V_RANK[rec.verification] < V_RANK[V_CORROBORATED]:
                events.append(Event("verification_changed", "model", rec.canonical_key, ts, rec.verification, V_CORROBORATED,
                                    reason=f"official announcement: {lead['title'][:140]}", run_id=run_id))
                rec.verification = V_CORROBORATED
    return events
