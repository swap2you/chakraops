# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — GET /api/ui/wheel/v2/decision TestClient."""

import pytest

try:
    from fastapi.testclient import TestClient
    from app.api.server import app

    _HAS_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore
    app = None  # type: ignore
    _HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI")


def test_wheel_v2_decision_requires_symbol():
    client = TestClient(app)
    resp = client.get("/api/ui/wheel/v2/decision")
    assert resp.status_code in (400, 422)


def test_wheel_v2_decision_returns_manual_only():
    client = TestClient(app)
    resp = client.get("/api/ui/wheel/v2/decision", params={"symbol": "SPY", "profile": "balanced"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "SPY"
    assert body["manual_only"] is True
    assert body["trade_execution"] is False
    assert body.get("phase")
    assert body.get("action")
    assert body.get("phase_label")
    assert "FAIL_" not in str(body)
    assert "WARN_" not in str(body)
    assert body.get("slack_payload", {}).get("manual_only") is True


def test_wheel_v2_decision_route_registered():
    client = TestClient(app)
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/ui/wheel/v2/decision" in paths
