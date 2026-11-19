"""Discovery sources. Each adapter turns one public catalogue into untrusted ``Observation`` rows.

No adapter needs an inference credential. Authority reflects who is speaking: a developer's own
repository outranks an aggregator that merely lists the model.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Callable, Optional, Protocol

from app.services.catalog import safe_http
from app.services.catalog.state import (AUTH_AGGREGATOR, AUTH_DEVELOPER, AUTH_OFFICIAL, DeveloperRecord, Observation, SourceState)

_DATA = Path(__file__).resolve().parents[2] / "data"
MAX_TEXT = 1200


@dataclass
class SourceResult:
    observations: list = field(default_factory=list)
    complete: bool = True                       # the response is believed to be the full list for its scope
    scope: Optional[set] = None                 # developer slugs fully covered this run (None = everything)
    raw_count: int = 0
    rejected: int = 0
    unregistered: dict = field(default_factory=dict)   # namespace -> count (developers we do not track)
    etag: Optional[str] = None
    cursor: Optional[str] = None
    not_modified: bool = False
    notes: list = field(default_factory=list)
    leads: list = field(default_factory=list)   # NEW announcement signals (become events); never become models on their own
    evidence: list = field(default_factory=list)   # every announcement inside the window: supporting evidence for models that already exist


class Source(Protocol):
    source_id: str
    kind: str
    default_interval_minutes: int

    def fetch(self, state: SourceState, developers: dict, now: datetime) -> SourceResult: ...


def _text(v: Any, limit: int = MAX_TEXT) -> Optional[str]:
    """Untrusted text -> bounded plain string (no markup interpretation is ever performed on it)."""
    if not isinstance(v, str):
        return None
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", v).strip()
    return cleaned[:limit] or None


def _int(v: Any) -> Optional[int]:
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _price_per_million(v: Any) -> Optional[float]:
    """Per-token decimal string -> USD per million tokens. Unknown or dynamic (-1) stays None, never zero."""
    try:
        if v is None or v == "":
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else round(f * 1_000_000, 6)


def _ts(v: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat() if v else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _iso_str(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


# ── OpenRouter: public aggregator catalogue (no key required) ──────────────────
class OpenRouterSource:
    source_id = "openrouter"
    kind = "public_aggregator"
    default_interval_minutes = 180
    URL = "https://openrouter.ai/api/v1/models"
    HOSTS = ("openrouter.ai",)

    def __init__(self, fetcher: Optional[Callable[..., safe_http.FetchResult]] = None):
        self._fetch = fetcher or safe_http.fetch_json

    def fetch(self, state: SourceState, developers: dict, now: datetime) -> SourceResult:
        res = self._fetch(self.URL, allowed_hosts=self.HOSTS, etag=state.etag)
        if res.not_modified:
            return SourceResult(not_modified=True, etag=state.etag, complete=False)
        rows = res.data.get("data") if isinstance(res.data, dict) else None
        if not isinstance(rows, list):
            raise safe_http.FetchError("malformed", "unexpected catalogue shape")
        return self.parse(rows, developers, etag=res.etag)

    def parse(self, rows: list, developers: dict, etag: Optional[str] = None) -> SourceResult:
        prefix_map = {p.lower(): d for d in developers.values() if d.enabled for p in d.openrouter_prefixes}
        out = SourceResult(raw_count=len(rows), etag=etag)
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or "/" not in row["id"]:
                out.rejected += 1
                continue
            if row["id"].startswith("~") or row.get("alias_target"):
                # Rolling aliases ("~openai/gpt-latest") point at another row; the target is the real model.
                out.rejected += 1
                continue
            prefix = row["id"].split("/", 1)[0].lower()
            dev: Optional[DeveloperRecord] = prefix_map.get(prefix)
            if dev is None:
                out.unregistered[prefix] = out.unregistered.get(prefix, 0) + 1
                continue
            arch = row.get("architecture") if isinstance(row.get("architecture"), dict) else {}
            top = row.get("top_provider") if isinstance(row.get("top_provider"), dict) else {}
            pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
            in_m = tuple(m for m in (arch.get("input_modalities") or []) if isinstance(m, str)) or _split_modality(arch.get("modality"), 0)
            out_m = tuple(m for m in (arch.get("output_modalities") or []) if isinstance(m, str)) or _split_modality(arch.get("modality"), 1)
            params = {p for p in (row.get("supported_parameters") or []) if isinstance(p, str)}
            caps = []
            if "tools" in params or "tool_choice" in params:
                caps.append("tool_calling")
            if "structured_outputs" in params or "response_format" in params:
                caps.append("structured_output")
            if "reasoning" in params or "include_reasoning" in params:
                caps.append("reasoning")
            if "image" in in_m:
                caps.append("image_understanding")
            if "audio" in in_m:
                caps.append("audio_input")
            if "file" in in_m:
                caps.append("file_input")
            price = {"input_per_million": _price_per_million(pricing.get("prompt")),
                     "output_per_million": _price_per_million(pricing.get("completion")),
                     "cache_read_per_million": _price_per_million(pricing.get("input_cache_read")), "currency": "USD"}
            if price["input_per_million"] is None and price["output_per_million"] is None:
                price = None
            urls = [{"kind": "provider_catalog", "url": f"https://openrouter.ai/{row['id']}", "label": "View on OpenRouter"}]
            hf = _text(row.get("hugging_face_id"), 200)
            if hf and re.fullmatch(r"[\w.\-]+/[\w.\-]+", hf):
                urls.append({"kind": "model_repository", "url": f"https://huggingface.co/{hf}", "label": "Model weights"})
            exp = _iso_str(row.get("expiration_date")) if isinstance(row.get("expiration_date"), str) else None
            out.observations.append(Observation(
                source_id=self.source_id, authority=AUTH_AGGREGATOR, offering_provider="OpenRouter", offering_model_id=row["id"],
                name=re.sub(r"\s*\((?:batch|free)\)\s*$", "", _text(row.get("name"), 200) or row["id"], flags=re.I), developer=dev.slug, description=_text(row.get("description")),
                released_at=_ts(row.get("created")), released_at_kind="listed_on_aggregator",
                context_window=_int(row.get("context_length") or top.get("context_length")), max_output_tokens=_int(top.get("max_completion_tokens")),
                input_modalities=in_m, output_modalities=out_m, capabilities=tuple(caps), pricing=price,
                open_weights=True if hf else None, urls=tuple(urls), expires_at=exp, benchmarks=_benchmarks(row.get("benchmarks")),
                deprecated=bool(exp and exp < datetime.now(timezone.utc).isoformat())))
        return out


_AA_METRICS = ("intelligence_index", "coding_index", "agentic_index")


def _benchmarks(raw: Any) -> Optional[dict]:
    """OpenRouter relays Artificial Analysis indices (0-100) per model. Kept only when numeric; absent stays absent."""
    aa = raw.get("artificial_analysis") if isinstance(raw, dict) else None
    if not isinstance(aa, dict):
        return None
    vals = {k: round(float(aa[k]), 2) for k in _AA_METRICS if isinstance(aa.get(k), (int, float)) and not isinstance(aa.get(k), bool) and 0 <= aa[k] <= 100}
    return {"source": "artificial_analysis", "via": "openrouter", "scale": "0-100", **vals} if "intelligence_index" in vals else None


def _split_modality(modality: Any, side: int) -> tuple:
    if not isinstance(modality, str) or "->" not in modality:
        return ()
    part = modality.split("->")[side]
    return tuple(p.strip() for p in re.split(r"[+,]", part) if p.strip())


# ── Hugging Face: developers' own public repositories (no key required) ────────
class HuggingFaceSource:
    source_id = "huggingface"
    kind = "developer_repository"
    default_interval_minutes = 720
    HOSTS = ("huggingface.co",)
    MAX_ORGS_PER_RUN = 6
    PER_ORG_LIMIT = 100
    MAX_PAGES = 3
    TIME_BUDGET_SECONDS = 20.0        # whole-source deadline: a slow upstream must not stall a serverless refresh
    _QUANT = re.compile(r"(?:^|[-_.])(gguf|awq|gptq|bnb|mlx|onnx|ggml|exl2|fp8|int4|int8|4bit|8bit|nvfp4|quantized|lora|adapter)(?:$|[-_.])", re.I)
    _TASK_OUT = {"text-generation": ("text",), "image-text-to-text": ("text",), "text2text-generation": ("text",), "feature-extraction": ("embeddings",),
                 "sentence-similarity": ("embeddings",), "text-to-image": ("image",), "text-to-video": ("video",), "text-to-speech": ("audio",),
                 "automatic-speech-recognition": ("text",), "any-to-any": ("text",), "image-to-text": ("text",)}
    _TASK_IN = {"image-text-to-text": ("text", "image"), "text-to-image": ("text",), "any-to-any": ("text", "image", "audio"),
                "automatic-speech-recognition": ("audio",), "image-to-text": ("image",)}

    def __init__(self, fetcher: Optional[Callable[..., safe_http.FetchResult]] = None):
        self._fetch = fetcher or safe_http.fetch_json

    def fetch(self, state: SourceState, developers: dict, now: datetime) -> SourceResult:
        orgs = [(d.slug, o) for d in developers.values() if d.enabled for o in d.huggingface_orgs]
        if not orgs:
            return SourceResult(complete=False, notes=["no registered Hugging Face organisations"])
        start = int(state.cursor) if state.cursor and state.cursor.isdigit() else 0
        picked = [orgs[(start + i) % len(orgs)] for i in range(min(self.MAX_ORGS_PER_RUN, len(orgs)))]
        result = SourceResult(cursor=str((start + len(picked)) % len(orgs)), scope=set(), complete=True)
        last_err: Optional[safe_http.FetchError] = None
        deadline = time.monotonic() + self.TIME_BUDGET_SECONDS
        for slug, org in picked:
            if time.monotonic() > deadline:
                result.complete = False
                result.notes.append(f"{org}: skipped (time budget)")
                continue
            url = f"https://huggingface.co/api/models?author={org}&sort=createdAt&direction=-1&limit={self.PER_ORG_LIMIT}"
            data: list = []
            more = False
            try:
                page_url: Optional[str] = url
                for page in range(self.MAX_PAGES):
                    if page and time.monotonic() > deadline:
                        more = True                      # stopped early: the list is NOT known to be complete
                        break
                    fetched = self._fetch(page_url, allowed_hosts=self.HOSTS)
                    if not isinstance(fetched.data, list):
                        raise safe_http.FetchError("malformed")
                    data += fetched.data
                    page_url = getattr(fetched, "next_url", None)
                    if not page_url:
                        break
                else:
                    more = True                          # page budget exhausted while a next page still exists
            except safe_http.FetchError as exc:
                last_err = exc
                result.complete = False
                result.notes.append(f"{org}: {exc.kind}")
                continue
            sub = self.parse(org, slug, data)
            result.observations += sub.observations
            result.raw_count += sub.raw_count
            result.rejected += sub.rejected
            if not more and len(fetched.data) < self.PER_ORG_LIMIT:   # no pending page and the last page was not full => the org's list is complete
                result.scope.add(slug)
        if not result.observations and last_err is not None:
            raise last_err
        return result

    def parse(self, org: str, slug: str, rows: list) -> SourceResult:
        out = SourceResult(raw_count=len(rows))
        for row in rows:
            rid = row.get("id") or row.get("modelId") if isinstance(row, dict) else None
            if not isinstance(rid, str) or "/" not in rid or row.get("private"):
                out.rejected += 1
                continue
            name = rid.split("/", 1)[1]
            task = row.get("pipeline_tag")
            if task not in self._TASK_OUT or self._QUANT.search(name):
                out.rejected += 1
                continue
            tags = [t for t in (row.get("tags") or []) if isinstance(t, str)]
            lic = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
            st = row.get("safetensors") if isinstance(row.get("safetensors"), dict) else {}
            out.observations.append(Observation(
                source_id=self.source_id, authority=AUTH_DEVELOPER, offering_provider="Hugging Face", offering_model_id=rid,
                name=name.replace("-", " ").replace("_", " ")[:200], developer=slug,
                released_at=_iso_str(row.get("createdAt")), released_at_kind="repository_created",
                input_modalities=self._TASK_IN.get(task, ("text",)), output_modalities=self._TASK_OUT[task],
                open_weights=True, license=_text(lic, 80), parameter_count=_int(st.get("total")),
                urls=({"kind": "model_repository", "url": f"https://huggingface.co/{rid}", "label": "Model weights and card"},)))
        return out


# ── Curated documentation snapshot (offline; ONE source among several) ─────────
class SeedSource:
    source_id = "curated_snapshot"
    kind = "documentation_snapshot"
    default_interval_minutes = 1440

    def __init__(self, path: Optional[Path] = None):
        self._path = path or (_DATA / "seed_catalog.json")

    def fetch(self, state: SourceState, developers: dict, now: datetime) -> SourceResult:
        payload = json.loads(self._path.read_text())
        out = SourceResult(raw_count=len(payload["models"]))
        for m in payload["models"]:
            dev = m.get("developer_slug")
            caps = tuple(m.get("capabilities") or ())
            out_m = ("embeddings",) if "embedding" in caps else tuple(m.get("modalities") or [m.get("modality", "text")])
            price = None
            if m.get("input_price_per_million") is not None or m.get("output_price_per_million") is not None:
                price = {"input_per_million": m.get("input_price_per_million"), "output_per_million": m.get("output_price_per_million"), "currency": "USD"}
            url = m.get("external_url") or m.get("provider_source")
            curated = {k: m.get(k) for k in ("estimated_quality", "estimated_cost", "estimated_latency", "reliability", "risk_level", "avg_latency_seconds",
                                             "fallback_priority", "supported_tasks", "supported_domains", "metric_provenance", "embedding_dimensions", "requires_key",
                                             "authentication_requirement", "cost_per_1k_tokens", "model_family", "fallback_priority") if k in m}
            tax = {k: m.get(k) for k in ("model_type", "use_categories", "weights_status", "license_name", "free_download", "free_access", "free_access_note",
                                         "deployment_options", "api_available", "taxonomy_status", "provider_role") if k in m}
            out.observations.append(Observation(
                source_id=self.source_id, authority=AUTH_OFFICIAL, offering_provider=m["provider"], offering_model_id=m["model_id"], name=m["model_name"],
                developer=dev, description=_text(m.get("description")), context_window=m.get("context_window") or None,
                input_modalities=tuple(m.get("modalities") or ["text"]), output_modalities=out_m, capabilities=caps, pricing=price,
                open_weights=True if m.get("weights_status") == "open_weights" else (False if m.get("weights_status") == "proprietary" else None),
                license=m.get("license_name"), urls=({"kind": "documentation", "url": url, "label": "Provider documentation"},) if url else (),
                curated=curated, taxonomy=tax))
        return out


# ── Official release announcements (RSS): discovery signals only ───────────────
class AnnouncementFeedSource:
    source_id = "announcements"
    kind = "release_feed"
    default_interval_minutes = 360

    def __init__(self, fetcher: Optional[Callable[..., safe_http.FetchResult]] = None):
        self._fetch = fetcher or safe_http.fetch_json

    def fetch(self, state: SourceState, developers: dict, now: datetime) -> SourceResult:
        from app.services.catalog import announcements
        since = None
        if state.cursor:
            try:
                since = datetime.fromisoformat(state.cursor)
            except ValueError:
                since = None
        feeds = [(d, u) for d in developers.values() if d.enabled for u in d.release_feeds]
        if not feeds:
            return SourceResult(complete=True, scope=set(), notes=["no release feeds registered"])
        res = SourceResult(complete=True, scope=set())
        newest, last_err, ok = since, None, 0
        for dev, url in feeds:
            host_ok = safe_http.safe_destination_url(url, dev.official_domains)          # a feed must live on the developer's own domains
            if not host_ok:
                res.notes.append(f"{dev.slug}: feed host is not an official domain")
                continue
            try:
                fetched = self._fetch(host_ok, allowed_hosts=(urlsplit(host_ok).hostname,), as_text=True)
            except safe_http.FetchError as exc:
                last_err = exc
                res.notes.append(f"{dev.slug}: {exc.kind}")
                continue
            if not isinstance(fetched.data, str):
                res.notes.append(f"{dev.slug}: malformed")
                continue
            ok += 1
            for item in announcements.parse_feed(fetched.data, since=None, now=now):          # whole window: evidence is re-evaluated every run
                row = {**item, "developer": dev.slug}
                res.evidence.append(row)
                stamp = datetime.fromisoformat(item["published_at"])
                if since is None or stamp > since:
                    res.leads.append(row)
                    newest = stamp if newest is None or stamp > newest else newest
        if not ok and last_err is not None:
            raise last_err
        if newest is not None:
            res.cursor = newest.isoformat()
        return res


def default_sources() -> list:
    return [SeedSource(), OpenRouterSource(), HuggingFaceSource(), AnnouncementFeedSource()]
