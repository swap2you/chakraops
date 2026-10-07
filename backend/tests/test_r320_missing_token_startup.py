"""R32.0: startup / provider state is fail-loud when the ORATS token is absent.

Verifies the documented startup contract without spinning heavy app lifecycle:
- A required token read raises a clear, value-free error when unset.
- Provider health reports BLOCKED_NO_TOKEN with no fallback provider.
- The read-only health endpoint surfaces the blocked state.
No fallback provider is ever introduced.
"""
import re

import pytest

from app.core.config import orats_secrets
from app.core.data_reliability.provider_health import provider_health_snapshot


def _clear_token(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_KEY", raising=False)


def test_required_token_fails_loud_without_value(monkeypatch):
    _clear_token(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        orats_secrets.get_orats_token(required=True)
    msg = str(exc.value)
    assert "ORATS_API_TOKEN is not set" in msg
    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-", msg)


def test_provider_health_blocked_without_token(monkeypatch):
    _clear_token(monkeypatch)
    snap = provider_health_snapshot()
    assert snap["token_present"] is False
    assert snap["status"] == "BLOCKED_NO_TOKEN"
    assert snap["blocked_reason"] == "TOKEN_ABSENT"
    assert snap["fallback_provider"] is None
    assert snap["sole_provider"] is True


def test_server_lifespan_uses_get_orats_token():
    # The startup path must resolve the token via the central env-only helper.
    import inspect
    from app.api import server

    src = inspect.getsource(server._lifespan)
    assert "get_orats_token" in src
    assert "UNAVAILABLE" in src  # probe status when token absent


def test_health_endpoint_reports_blocked(monkeypatch):
    _clear_token(monkeypatch)
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    resp = client.get("/api/ui/data-reliability/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]["status"] == "BLOCKED_NO_TOKEN"
    assert body["provider"]["fallback_provider"] is None
    assert body["earnings_calendar"]["state"] == "UNAVAILABLE"
