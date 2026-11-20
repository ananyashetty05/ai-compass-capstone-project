"""Safety boundary for tests that touch persistence.

Database tests run only when TEST_DATABASE_URL points to an isolated Neon branch
or separate database.  They never inherit DATABASE_URL, which may be production.
"""
import os

_test_database_url = os.environ.get("TEST_DATABASE_URL", "").strip()
os.environ["DATABASE_URL"] = _test_database_url
# Tests never inherit a developer's local catalogue switches either (explicit environment beats .env).
os.environ["CATALOG_PERSISTENCE_ENABLED"] = "false"
os.environ["CRON_SECRET"] = ""
HAS_ISOLATED_TEST_DATABASE = bool(_test_database_url)


# ── Pool source ───────────────────────────────────────────────────────────────────────────────────────────────────────
# Production default is the approved ecosystem pool (POOL_SOURCE=approved). The pre-existing suites exercise the legacy live-catalogue
# path, which stays available as POOL_SOURCE=live, so they run against it. Modules named test_approved_* run against the approved pool.
import pytest


@pytest.fixture(autouse=True)
def _pool_source(request):
    from app.core.config import settings
    previous = settings.POOL_SOURCE
    settings.POOL_SOURCE = "approved" if "test_approved" in request.module.__name__ else "live"
    try:
        from app.services import registry_service
        registry_service.invalidate_cache()
    except Exception:
        pass
    yield
    settings.POOL_SOURCE = previous
