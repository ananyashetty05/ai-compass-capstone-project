"""Family / generation classification from model identifiers and display names.

Generic by construction: no vendor or model names are listed here. The only vocabulary is the
shared naming conventions in ``data/naming_rules.json`` (variant words, packaging labels, release
stages) plus optional per-developer ``family_includes`` from ``data/developers.json``.

Versions are *structured tuples*, never strings: ``3.10`` is newer than ``3.9``. A model whose
generation cannot be established is reported as such (``kind == 'none'``) instead of guessed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parents[2] / "data"

_SIZE = re.compile(r"^(?:\d+(?:\.\d+)?[bkmt]|\d+x\d+(?:\.\d+)?b|a\d+(?:\.\d+)?b|e\d+b)$")
_ALNUM = re.compile(r"^([a-z]+)(\d+(?:\.\d+)?)([a-z]{0,2})$")          # qwen3, o3, r1, gpt4, qwen2.5
_NUMALPHA = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)([a-z]{1,2})$")        # 4o, 2.5v
_VER = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")
_VP = re.compile(r"^v(\d{1,2})p(\d{1,2})$")                              # fireworks style: v3p3
_DATE_PATTERNS = [
    re.compile(r"(?<!\d)20\d{2}[-_.]\d{2}[-_.]\d{2}(?!\d)"),             # 2024-04-09
    re.compile(r"(?<!\d)20\d{6}(?!\d)"),                                 # 20241022
    re.compile(r"(?<!\d)\d{2}[-_.]20\d{2}(?!\d)"),                       # 08-2024
]
_FOUR = re.compile(r"(?<![\d.])(\d{4})(?![\d.]|[a-z])")
_THREE = re.compile(r"^\d{3}$")
_NO_MINOR_SUFFIX = set("bkmt")


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads((_DATA / "naming_rules.json").read_text())


@dataclass(frozen=True)
class Classification:
    developer: Optional[str]
    family: str
    track: str                       # text | image | audio | video | embedding
    kind: str                        # version | date | none
    version: tuple = ()
    label: Optional[str] = None
    variants: tuple = ()
    size: Optional[str] = None
    stage: Optional[str] = None
    revision: Optional[str] = None
    canonical_slug: str = ""
    confidence: str = "low"          # high | medium | low
    notes: tuple = ()

    @property
    def lineage_key(self) -> str:
        return f"{self.developer or 'unknown'}:{self.family}:{self.track}"

    @property
    def generation_key(self) -> Optional[str]:
        return f"{self.lineage_key}@{self.label}" if self.kind != "none" and self.label else None

    @property
    def sort_key(self) -> tuple:
        return self.version if self.kind != "none" else ()


def _norm_version(parts: tuple) -> tuple:
    out = list(parts)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return tuple(out)


def _label(parts: tuple) -> str:
    return ".".join(str(p) for p in parts)


def _clean(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.rsplit("/", 1)[-1]                                  # org/ and accounts/x/models/ prefixes
    s = re.sub(r"^[a-z0-9]+\.(?=[a-z])", "", s)               # bedrock 'amazon.' prefix
    s = re.sub(r":\d+$", "", s)                               # ':0' version suffix
    return s.replace(":", "-")


def _extract_revision(s: str) -> tuple[str, Optional[str]]:
    for pat in _DATE_PATTERNS:
        m = pat.search(s)
        if m:
            return (s[:m.start()] + " " + s[m.end():]), m.group(0)
    return s, None


def _tokens(s: str) -> list[str]:
    s, _ = s, None
    s = re.sub(r"[\s_/]+", "-", s)
    return [t for t in re.split(r"-+", s) if t]


def parse(raw: str, developer: Optional[str], family_includes: tuple = (), out_modalities: tuple = ()) -> Classification:
    cfg = rules()
    variant_words, ignored, stages = set(cfg["variant"]), set(cfg["ignored"]), set(cfg["stage"])
    s, revision = _extract_revision(_clean(raw))
    notes: list[str] = []
    raw_tokens = _tokens(s)

    # Expand merged tokens: qwen3 -> qwen,3 ; o3 -> o,3 ; 4o -> 4,o ; v3p3 -> 3.3 ; lone 'v' before a number is a marker.
    toks: list[tuple[str, str]] = []   # (kind, text) kind in alpha|num|size|stage|rev
    pending_v = False
    for t in raw_tokens:
        if _SIZE.match(t):
            toks.append(("size", t)); continue
        m = _VP.match(t)
        if m:
            toks.append(("num", f"{m.group(1)}.{m.group(2)}")); continue
        m = _ALNUM.match(t)
        if m and not _SIZE.match(t):
            toks.append(("alpha", m.group(1)))
            toks.append(("num", m.group(2)))
            if m.group(3):
                toks.append(("alpha", m.group(3)))
            continue
        m = _NUMALPHA.match(t)
        if m and m.group(2)[0] not in _NO_MINOR_SUFFIX:
            toks.append(("num", m.group(1))); toks.append(("alpha", m.group(2))); continue
        if _VER.match(t):
            toks.append(("num", t)); continue
        if _THREE.match(t):
            revision = revision or t; continue
        if re.fullmatch(r"\d{4}", t):
            revision = revision or t; continue
        if re.fullmatch(r"\d+", t):
            notes.append(f"ignored numeric token {t}"); continue
        if t in stages:
            toks.append(("stage", t)); continue
        toks.append(("alpha", t))
    # a lone 'v' directly before a number is a version marker, not part of the family
    cleaned: list[tuple[str, str]] = []
    for i, (k, t) in enumerate(toks):
        if k == "alpha" and t == "v" and i + 1 < len(toks) and toks[i + 1][0] == "num":
            continue
        cleaned.append((k, t))
    toks = cleaned

    # version = first numeric token; a following 1-2 digit integer is its minor part (claude-3-5)
    ver: tuple = ()
    ver_idx = None
    for i, (k, t) in enumerate(toks):
        if k == "num":
            parts = tuple(int(p) for p in t.split("."))
            ver_idx = i
            if len(parts) == 1 and i + 1 < len(toks) and toks[i + 1][0] == "num" and "." not in toks[i + 1][1]:
                parts = (parts[0], int(toks[i + 1][1]))
                toks[i + 1] = ("consumed", toks[i + 1][1])
            ver = _norm_version(parts)
            break

    family_tokens: list[str] = []
    variants: list[str] = []
    pre_tokens: list[str] = []
    size = None
    stage = None
    includes = set(family_includes)
    for i, (k, t) in enumerate(toks):
        if k in ("consumed", "num"):
            continue
        if k == "size":
            size = size or t; continue
        if k == "stage":
            stage = stage or t; continue
        before_version = ver_idx is None or i < ver_idx
        if before_version:
            pre_tokens.append(t)
        if t in ignored:
            continue
        if t in includes:
            family_tokens.append(t); continue
        if t in variant_words:
            variants.append(t); continue
        if before_version:
            family_tokens.append(t)
        else:
            variants.append(t)       # identity-bearing token after the version (e.g. nemotron, distill)

    if not family_tokens and pre_tokens:
        family_tokens = list(pre_tokens)     # e.g. text-embedding-3-small: the family is the descriptive stem
    family = "-".join(dict.fromkeys(family_tokens)) or (developer or "unknown")
    variants = [v for v in variants if v not in family.split("-")]
    kind, label, confidence = "none", None, "low"
    if ver:
        kind, label, confidence = "version", _label(ver), "high" if developer else "medium"
    elif revision and re.fullmatch(r"\d{4}", revision):
        yy, mm = int(revision[:2]), int(revision[2:])
        if 23 <= yy <= 40 and 1 <= mm <= 12:
            kind, ver, label, confidence = "date", (2000 + yy, mm), revision, "medium"
            notes.append("generation is date-based")
    if kind == "none":
        notes.append("no generation marker found")

    uniq_variants = tuple(sorted(dict.fromkeys(variants)))
    slug_parts = [family] + ([label] if label and kind == "version" else []) + list(uniq_variants) + ([size] if size else []) + ([stage] if stage else [])
    if kind == "date":
        slug_parts.insert(1, label)
    elif kind == "none" and revision:
        slug_parts.append(f"r{revision}")
    return Classification(
        developer=developer, family=family, track=_track(toks, out_modalities), kind=kind, version=ver if kind != "none" else (),
        label=label, variants=uniq_variants, size=size, stage=stage, revision=revision,
        canonical_slug="-".join(p for p in slug_parts if p), confidence=confidence, notes=tuple(notes),
    )


def _track(toks: list[tuple[str, str]], out_modalities: tuple) -> str:
    cfg = rules()
    words = {t for k, t in toks if k == "alpha"}
    out = {m.lower() for m in out_modalities}
    if "embeddings" in out or "embedding" in out or words & set(cfg["embedding_words"]):
        return "embedding"
    if "image" in out and ("text" not in out or words & set(cfg["image_words"])):
        return "image"
    if "video" in out and "text" not in out:
        return "video"
    if "audio" in out and "text" not in out:
        return "audio"
    if not out:
        if words & set(cfg["image_words"]) - {"image"} or ("image" in words and "gpt" in words):
            return "image"
        if words & set(cfg["video_words"]):
            return "video"
        if words & set(cfg["audio_words"]) - {"audio", "voice"}:
            return "audio"
    return "text"


def classify(model_id: str, name: str, developer: Optional[str], *, family_includes: tuple = (), out_modalities: tuple = ()) -> Classification:
    """Prefer the identifier; fall back to the display name when the id carries no generation."""
    by_id = parse(model_id, developer, family_includes, out_modalities)
    if by_id.kind != "none" or not name:
        return by_id
    by_name = parse(name, developer, family_includes, out_modalities)
    return by_name if by_name.kind != "none" else by_id


def newer(a: Classification, b: Classification) -> bool:
    """True when ``a`` is a later generation than ``b`` in the same lineage (structured comparison)."""
    return a.kind == b.kind != "none" and a.version > b.version
