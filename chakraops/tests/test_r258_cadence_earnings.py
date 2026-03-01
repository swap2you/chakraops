# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.8: Cadence discipline + earnings debug — safe schema, no FAIL_/WARN_, no new persisted fields."""

from __future__ import annotations

import json
from unittest.mock import patch


def test_earnings_debug_safe_schema_no_fail_warn() -> None:
    """R25.8: GET /api/ui/earnings/debug returns safe fields only; no FAIL_/WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/earnings/debug", params={"symbol": "NVDA"})
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] in ("OK", "Unavailable", "Stale")
    assert "next_date" in data
    assert "days" in data
    assert "implied_move_pct" in data
    assert "as_of" in data
    raw = json.dumps(data)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
    assert "Not evaluated" not in raw


def test_earnings_debug_blank_symbol_returns_unavailable() -> None:
    """R25.8: Blank symbol (after strip) => 200 with status Unavailable."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/earnings/debug", params={"symbol": "  "})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "Unavailable"
    assert data.get("next_date") is None


def test_system_health_includes_cadence_and_earnings_probe_symbol() -> None:
    """R25.8: GET /api/ui/system-health includes cadence and earnings_probe_symbol."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    assert "cadence" in data
    cadence = data["cadence"]
    assert "mode" in cadence
    assert cadence["mode"] in ("EOD_BIASED", "LIVE")
    assert "earnings_probe_symbol" in data
    assert isinstance(data["earnings_probe_symbol"], str)
    raw = json.dumps(data)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
