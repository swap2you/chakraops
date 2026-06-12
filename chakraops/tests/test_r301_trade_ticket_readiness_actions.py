# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.1: Trade ticket readiness action links — per-check action_label/action_href; safe; no decision write; order unchanged."""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")

CHECK_CODES = ["INTEGRITY", "MARK_FRESHNESS", "CASH_SECURED_RESERVE", "SIZING_CONSTRAINTS", "EARNINGS_ADVISORY", "ACCOUNT_PRESENT"]

EXPECTED_ACTIONS = {
    "INTEGRITY": ("Open integrity", "/positions?source=db&symbol="),
    "MARK_FRESHNESS": ("Open system diagnostics", "/system"),
    "CASH_SECURED_RESERVE": ("Open portfolio", "/portfolio"),
    "SIZING_CONSTRAINTS": ("Open guardrails", "/system"),
    "EARNINGS_ADVISORY": ("Open symbol", "/symbol-diagnostics?symbol="),
    "ACCOUNT_PRESENT": ("Open settings", "/system"),
}


def test_readiness_includes_action_links_per_check() -> None:
    """Each check has action_label and action_href; INTEGRITY and EARNINGS_ADVISORY hrefs include symbol."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/trade-ticket/readiness",
        params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY"},
    )
    assert r.status_code == 200
    data = r.json()
    checks = data.get("checks") or []
    assert len(checks) == len(CHECK_CODES)
    for c in checks:
        code = c.get("code")
        assert code in CHECK_CODES
        assert "action_label" in c, f"Missing action_label for {code}"
        assert "action_href" in c, f"Missing action_href for {code}"
        expected_label, expected_href_prefix = EXPECTED_ACTIONS[code]
        assert c["action_label"] == expected_label
        assert c["action_href"].startswith(expected_href_prefix) or c["action_href"] == expected_href_prefix
    integrity = next(c for c in checks if c["code"] == "INTEGRITY")
    assert "SPY" in integrity["action_href"] or "symbol=SPY" in integrity["action_href"]
    earnings = next(c for c in checks if c["code"] == "EARNINGS_ADVISORY")
    assert "SPY" in earnings["action_href"] or "symbol=SPY" in earnings["action_href"]


def test_readiness_action_links_safe_no_forbidden_tokens() -> None:
    """Response JSON has no \\b(FAIL|WARN|PASS)\\b or FAIL_/WARN_ in any string."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/trade-ticket/readiness",
        params={"symbol": "AAPL", "mode": "paper", "ticket_kind": "CC"},
    )
    assert r.status_code == 200
    raw = json.dumps(r.json(), default=str)
    assert not FORBIDDEN.search(raw)
    assert not FORBIDDEN_UNDERSCORE.search(raw)


def test_readiness_actions_do_not_write_decision_latest(tmp_path) -> None:
    """GET trade-ticket/readiness does not create or modify out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/trade-ticket/readiness", params={"symbol": "SPY", "ticket_kind": "ENTRY"})
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_readiness_checks_order_unchanged() -> None:
    """Checks remain in fixed order: INTEGRITY, MARK_FRESHNESS, CASH_SECURED_RESERVE, SIZING_CONSTRAINTS, EARNINGS_ADVISORY, ACCOUNT_PRESENT."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/trade-ticket/readiness", params={"symbol": "SPY", "ticket_kind": "ENTRY"})
    assert r.status_code == 200
    codes = [c["code"] for c in (r.json().get("checks") or [])]
    assert codes == CHECK_CODES
