"""Auth registration / login hardening. Needs TEST_DATABASE_URL (see conftest)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    import os
    from app.core.config import settings
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret")
    from app.services import user_store
    user_store.init_db()
    from app.main import app
    return TestClient(app)


def _body(email="v@example.com", **kw):
    b = {"name": "Ada", "email": kw.pop("email", email), "password": "correct-horse", "user_group": "student"}
    b.update(kw)
    return b


def test_register_login_roundtrip_and_case_insensitive(client):
    r = client.post("/api/v1/auth/register", json=_body("Ada.Case@Example.com"))
    assert r.status_code == 201, r.text
    assert r.json()["profile"]["email"] == "ada.case@example.com"
    r = client.post("/api/v1/auth/login", json={"email": "ADA.case@example.com ", "password": "correct-horse"})
    assert r.status_code == 200 and r.json()["token"]
    assert client.post("/api/v1/auth/login", json={"email": "ada.case@example.com", "password": "nope"}).status_code == 401


def test_duplicate_email_is_409(client):
    assert client.post("/api/v1/auth/register", json=_body("dup@example.com")).status_code == 201
    r = client.post("/api/v1/auth/register", json=_body("DUP@example.com"))
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


@pytest.mark.parametrize("patch", [
    {"email": "not-an-email"}, {"password": "short"}, {"name": "   "},
    {"user_group": "wizard"}, {"routing_preferences": {"quality": 7}},
])
def test_invalid_payloads_are_422(client, patch):
    assert client.post("/api/v1/auth/register", json=_body(**patch)).status_code == 422


def test_missing_database_url_gives_clear_503(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    r = client.post("/api/v1/auth/register", json=_body("nodb@example.com"))
    assert r.status_code == 503 and "DATABASE_URL" in r.json()["detail"]
