"""Bounded, SSRF-resistant HTTPS fetching for discovery sources.

Only hosts named in a source's allow-list are contacted, over HTTPS on port 443, with no
credentials in the URL, no redirects to other hosts, a hard timeout and a response-size cap.
Hostnames are resolved first and refused if any address is private, loopback, link-local,
multicast or otherwise non-public. All returned data is untrusted and is parsed as JSON only;
nothing fetched is ever executed.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

import httpx

USER_AGENT = "AI-Compass-CatalogBot/1.0 (+public model metadata discovery; respects rate limits)"
MAX_BYTES_DEFAULT = 12 * 1024 * 1024


class FetchError(Exception):
    """Classified failure. ``kind`` is safe to show; upstream bodies are never included."""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


@dataclass
class FetchResult:
    status: int
    data: Any
    etag: Optional[str]
    not_modified: bool = False
    next_url: Optional[str] = None            # RFC 8288 rel="next" (pagination); validated by the caller's allow-list on use


def _public_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


def validate_url(url: str, allowed_hosts: Iterable[str]) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchError("blocked", "only https is allowed")
    if parts.username or parts.password:
        raise FetchError("blocked", "credentials in URL")
    host = (parts.hostname or "").lower()
    if not host or host not in {h.lower() for h in allowed_hosts}:
        raise FetchError("blocked", "host is not allow-listed")
    if parts.port not in (None, 443):
        raise FetchError("blocked", "port not allowed")
    try:
        ipaddress.ip_address(host)
        raise FetchError("blocked", "IP literals are not allowed")
    except ValueError:
        pass
    return host


def _resolve_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("network", "DNS resolution failed") from exc
    if not infos or not all(_public_ip(i[4][0]) for i in infos):
        raise FetchError("blocked", "host resolves to a non-public address")


def _next_link(header: Optional[str], base: str) -> Optional[str]:
    if not header:
        return None
    for part in header.split(","):
        m = re.match(r'\s*<([^>]+)>\s*;.*rel="?next"?', part)
        if m:
            return str(httpx.URL(base).join(m.group(1)))
    return None


def classify_http(exc: Exception) -> FetchError:
    if isinstance(exc, FetchError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return FetchError("timeout")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return FetchError("rate_limited" if code == 429 else "http_error", f"HTTP {code}")
    if isinstance(exc, (httpx.TransportError, OSError)):
        return FetchError("network")
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return FetchError("malformed")
    return FetchError("unknown")


def fetch_json(url: str, *, allowed_hosts: Iterable[str], timeout: float = 12.0, max_bytes: int = MAX_BYTES_DEFAULT,
               etag: Optional[str] = None, headers: Optional[dict] = None, client: Optional[httpx.Client] = None,
               resolve: bool = True, as_text: bool = False) -> FetchResult:
    """GET ``url`` and parse JSON. Raises :class:`FetchError` with a classified, safe ``kind``."""
    hosts = list(allowed_hosts)
    current = url
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        for _ in range(4):
            host = validate_url(current, hosts)
            if resolve:
                _resolve_public(host)
            req_headers = dict(headers or {})
            if etag:
                req_headers["If-None-Match"] = etag
            try:
                with http.stream("GET", current, headers=req_headers, timeout=timeout) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        current = str(httpx.URL(current).join(resp.headers.get("location", "")))
                        continue            # re-validated against the allow-list at the top of the loop
                    if resp.status_code == 304:
                        return FetchResult(304, None, etag, True)
                    resp.raise_for_status()
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError("too_large")
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise FetchError("too_large")
                    return FetchResult(resp.status_code, bytes(body).decode("utf-8", "replace") if as_text else json.loads(bytes(body)), resp.headers.get("etag"), False, _next_link(resp.headers.get("link"), current))
            except Exception as exc:  # classified below; upstream text is never propagated
                raise classify_http(exc) from None
        raise FetchError("blocked", "too many redirects")
    finally:
        if own:
            http.close()


def safe_destination_url(url: Optional[str], allowed_domains: Iterable[str]) -> Optional[str]:
    """A URL may be shown as an official destination only if it is https and on an allowed domain."""
    if not url or len(url) > 500:
        return None
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or not host:
        return None
    for dom in allowed_domains:
        d = dom.lower()
        if host == d or host.endswith("." + d):
            return parts.geturl()
    return None
