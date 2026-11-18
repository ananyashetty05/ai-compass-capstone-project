import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

from app.services.model_adapters.provider_adapters import _safe_provider_error


class FakeError(Exception):
    def __init__(self, status_code=None):
        self.status_code = status_code


def test_rate_limit_is_retryable_and_safe():
    error = _safe_provider_error("Provider", FakeError(429))
    assert error.kind == "rate_limited"
    assert error.retryable is True


def test_authentication_and_invalid_model_are_not_retryable():
    assert _safe_provider_error("Provider", FakeError(401)).retryable is False
    assert _safe_provider_error("Provider", FakeError(404)).kind == "invalid_model"


def test_unknown_errors_do_not_expose_upstream_details():
    error = _safe_provider_error("Provider", Exception("secret upstream detail"))
    assert "secret upstream detail" not in str(error)
