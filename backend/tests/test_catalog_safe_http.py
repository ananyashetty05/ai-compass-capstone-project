"""fetch_json behaviour against an in-process transport (no network)."""
import httpx
import pytest

from app.services.catalog import safe_http
from app.services.catalog.safe_http import FetchError

HOSTS = ["openrouter.ai"]
URL = "https://openrouter.ai/api/v1/models"


def fetch(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return safe_http.fetch_json(URL, allowed_hosts=HOSTS, client=client, resolve=False, **kw)


def test_success_returns_json_and_etag():
    r = fetch(lambda req: httpx.Response(200, json={"data": []}, headers={"etag": 'W/"a"'}))
    assert r.data == {"data": []} and r.etag == 'W/"a"' and not r.not_modified


def test_conditional_request_sends_etag_and_handles_304():
    seen = {}

    def handler(req):
        seen["inm"] = req.headers.get("if-none-match")
        return httpx.Response(304)
    r = fetch(handler, etag='W/"a"')
    assert r.not_modified and seen["inm"] == 'W/"a"'


@pytest.mark.parametrize("status,kind", [(429, "rate_limited"), (500, "http_error"), (404, "http_error")])
def test_http_errors_are_classified_without_leaking_bodies(status, kind):
    with pytest.raises(FetchError) as e:
        fetch(lambda req: httpx.Response(status, text="secret upstream detail"))
    assert e.value.kind == kind and "secret" not in str(e.value)


def test_oversized_and_malformed_bodies_are_rejected():
    with pytest.raises(FetchError) as e:
        fetch(lambda req: httpx.Response(200, content=b"[" + b"1," * 5000 + b"1]"), max_bytes=1000)
    assert e.value.kind == "too_large"
    with pytest.raises(FetchError) as e2:
        fetch(lambda req: httpx.Response(200, content=b"<html>not json</html>"))
    assert e2.value.kind == "malformed"


def test_redirect_to_another_host_is_blocked_and_same_host_followed():
    with pytest.raises(FetchError) as e:
        fetch(lambda req: httpx.Response(302, headers={"location": "https://evil.example/x"}))
    assert e.value.kind == "blocked"

    def handler(req):
        if req.url.path == "/api/v1/models":
            return httpx.Response(302, headers={"location": "/api/v2/models"})
        return httpx.Response(200, json={"ok": True})
    assert fetch(handler).data == {"ok": True}


def test_timeout_is_classified():
    def handler(req):
        raise httpx.ReadTimeout("slow")
    with pytest.raises(FetchError) as e:
        fetch(handler)
    assert e.value.kind == "timeout"


def test_dns_resolving_to_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    with pytest.raises(FetchError) as e:
        safe_http.fetch_json(URL, allowed_hosts=HOSTS, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    assert e.value.kind == "blocked"
