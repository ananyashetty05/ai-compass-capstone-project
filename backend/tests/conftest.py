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
