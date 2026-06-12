# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.0: Trade ticket readiness endpoint — safe labels only, deterministic ordering, no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")

CHECK_CODES = ["INTEGRITY", "MARK_FRESHNESS", "CASH_SECURED_RESERVE", "SIZING_CONSTRAINTS", "EARNINGS_ADVISORY", "ACCOUNT_PRESENT"]


def test_readiness_safe_labels_only() -> None:
    """GET /api/ui/trade-ticket/readiness response contains no FAIL/WARN/PASS or FAIL_/WARN_."""
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
    raw = json.dumps(data, default=str)
    assert not FORBIDDEN.search(raw), "Response contained forbidden whole-word token"
    assert not FORBIDDEN_UNDERSCORE.search(raw), "Response contained FAIL_/WARN_"


def test_readiness_deterministic_ordering() -> None:
    """Checks and order_stub.lines have deterministic order."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r1 = client.get("/api/ui/trade-ticket/readiness", params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY"})
    r2 = client.get("/api/ui/trade-ticket/readiness", params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    codes1 = [c["code"] for c in (d1.get("checks") or [])]
    codes2 = [c["code"] for c in (d2.get("checks") or [])]
    assert codes1 == codes2
    assert codes1 == CHECK_CODES
    stub1 = d1.get("order_stub") or {}
    stub2 = d2.get("order_stub") or {}
    assert isinstance(stub1.get("lines"), list)
    assert isinstance(stub2.get("lines"), list)
    assert len(stub1["lines"]) == len(stub2["lines"])


def test_readiness_does_not_write_decision_latest(tmp_path) -> None:
    """GET trade-ticket/readiness does not create or modify out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/trade-ticket/readiness", params={"symbol": "AAPL", "mode": "paper", "ticket_kind": "CC"})
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_readiness_response_shape() -> None:
    """Response has status, status_label, as_of_utc, checks, order_stub with title and lines."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/trade-ticket/readiness", params={"symbol": "SPY", "ticket_kind": "ENTRY"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") in ("OK", "Review")
    assert "status_label" in data
    assert "as_of_utc" in data
    checks = data.get("checks") or []
    assert len(checks) == len(CHECK_CODES)
    for c in checks:
        assert c.get("code") in CHECK_CODES
        assert c.get("status") in ("OK", "Review")
        assert "label" in c
        assert "detail" in c
    stub = data.get("order_stub") or {}
    assert "title" in stub
    assert "lines" in stub
    assert isinstance(stub["lines"], list)
