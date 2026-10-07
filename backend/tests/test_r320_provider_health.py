"""R32.0: ORATS provider health visibility, failure classification, contract."""
from app.core.config import orats_secrets
from app.core.data_reliability.provider_health import (
    AUTH,
    INVALID_RESPONSE,
    NETWORK,
    NO_DATA,
    RATE_LIMIT,
    UNAVAILABLE,
    UNKNOWN,
    classify_provider_failure,
    provider_health_snapshot,
    validate_read_only_contract,
)
from app.core.options.providers.orats_client import (
    OratsAuthError,
    OratsDataUnavailableError,
)


def test_classify_by_http_status():
    assert classify_provider_failure(http_status=401) == AUTH
    assert classify_provider_failure(http_status=403) == AUTH
    assert classify_provider_failure(http_status=429) == RATE_LIMIT
    assert classify_provider_failure(http_status=404) == NO_DATA
    assert classify_provider_failure(http_status=500) == UNAVAILABLE


def test_classify_by_exception_type():
    assert classify_provider_failure(OratsAuthError(401, "x")) == AUTH
    assert classify_provider_failure(
        OratsDataUnavailableError("strikes", "SPY", 403)
    ) == AUTH  # 403 status wins
    assert classify_provider_failure(ValueError("bad json")) == INVALID_RESPONSE
    assert classify_provider_failure(TimeoutError("t")) == NETWORK


def test_classify_unknown_does_not_guess_benign():
    assert classify_provider_failure(None, None) == UNKNOWN
    assert classify_provider_failure(Exception("?")) == UNKNOWN


def test_read_only_contract_has_no_mutating_endpoints():
    c = validate_read_only_contract()
    assert c.ok is True
    assert c.violations == []
    assert "strikes" in c.allowed_endpoints
    assert c.to_dict()["method"] == "GET"
    assert c.to_dict()["mutating_endpoints"] is False


def test_snapshot_reports_token_present(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", "present-token")
    snap = provider_health_snapshot()
    assert snap["provider"] == "ORATS"
    assert snap["sole_provider"] is True
    assert snap["fallback_provider"] is None
    assert snap["token_present"] is True
    assert snap["status"] == "READY"
    # Never leak the value.
    assert "present-token" not in str(snap)
    assert snap["retry_policy"]["retry_on_status"] == [429]
    assert snap["cache_policy"]["market_data_cached"] is False


def test_snapshot_blocked_without_token(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_KEY", raising=False)
    snap = provider_health_snapshot()
    assert snap["token_present"] is False
    assert snap["status"] == "BLOCKED_NO_TOKEN"
    assert snap["blocked_reason"] == "TOKEN_ABSENT"
