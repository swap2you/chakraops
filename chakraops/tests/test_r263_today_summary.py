# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.3: Today summary — GET /api/ui/today/summary schema and no FAIL_/WARN_."""

from __future__ import annotations

import json
from unittest.mock import patch


def test_today_summary_returns_expected_schema() -> None:
    """Today summary endpoint returns expected structure."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/today/summary")
    assert r.status_code == 200
    data = r.json()
    assert "latest_run_ts" in data
    assert "as_of_et" in data
    assert "cadence" in data
    assert isinstance(data["cadence"], dict)
    assert "mode" in data["cadence"]
    assert "eligibility_as_of" in data["cadence"]
    assert "orats_status" in data
    assert "guardrails" in data
    assert "notifications_health" in data
    assert "notifications_new_count" in data
    assert isinstance(data["notifications_new_count"], int)
    assert "earnings_probe" in data
    assert isinstance(data["earnings_probe"], dict)
    assert "action_needed_count" in data


def test_today_summary_no_fail_warn_in_json() -> None:
    """Today summary response must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/today/summary")
    assert r.status_code == 200
    raw = json.dumps(r.json())
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
