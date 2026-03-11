# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.2: Readiness pack endpoint — ZIP contents, no forbidden tokens, deterministic, no decision write."""

from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")

EXPECTED_ZIP_NAMES = [
    "manifest.json",
    "readiness.json",
    "system_health_subset.json",
    "notes.json",
]


def _fixed_readiness(*, symbol: str, mode: str, ticket_kind: str):
    return {
        "status": "OK",
        "status_label": "All checks OK",
        "as_of_utc": "2026-02-27T12:00:00Z",
        "checks": [
            {"code": "INTEGRITY", "status": "OK", "label": "OK", "detail": ""},
            {"code": "MARK_FRESHNESS", "status": "OK", "label": "OK", "detail": ""},
            {"code": "CASH_SECURED_RESERVE", "status": "OK", "label": "OK", "detail": ""},
            {"code": "SIZING_CONSTRAINTS", "status": "OK", "label": "No constraints hit", "detail": ""},
            {"code": "EARNINGS_ADVISORY", "status": "OK", "label": "OK", "detail": ""},
            {"code": "ACCOUNT_PRESENT", "status": "OK", "label": "Default account set", "detail": ""},
        ],
        "order_stub": {"title": "Order stub: SPY CSP OPEN", "lines": ["Symbol: SPY", "Strategy: CSP", "Action: OPEN", "Qty: 2"]},
    }


def _fixed_health_block():
    return {"status": "OK", "status_label": "OK"}


def test_pack_zip_contains_expected_files() -> None:
    """GET /api/ui/trade-ticket/readiness-pack returns a ZIP with manifest, readiness, system_health_subset, notes."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/trade-ticket/readiness-pack",
        params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY", "include_paper": True},
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    assert "attachment" in (r.headers.get("content-disposition") or "")
    assert "readiness_pack_" in (r.headers.get("content-disposition") or "")
    assert "SPY" in (r.headers.get("content-disposition") or "")
    z = zipfile.ZipFile(BytesIO(r.content), "r")
    names = set(z.namelist())
    for expected in EXPECTED_ZIP_NAMES:
        assert expected in names, f"Missing {expected}"
    z.close()


def test_pack_contains_no_forbidden_tokens() -> None:
    """All JSON file contents in the pack contain no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/trade-ticket/readiness-pack",
        params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY", "include_paper": True},
    )
    assert r.status_code == 200
    z = zipfile.ZipFile(BytesIO(r.content), "r")
    for name in EXPECTED_ZIP_NAMES:
        if name not in z.namelist():
            continue
        raw = z.read(name).decode("utf-8")
        assert not FORBIDDEN.search(raw), f"{name} contained forbidden whole-word token: {raw[:200]}"
        assert not FORBIDDEN_UNDERSCORE.search(raw), f"{name} contained FAIL_/WARN_: {raw[:200]}"
    z.close()


def test_pack_deterministic_for_fixed_fixture() -> None:
    """Same inputs yield identical parsed JSON contents (manifest generated_at excluded for comparison)."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._build_trade_ticket_readiness", side_effect=lambda **kw: _fixed_readiness(**kw)), \
         patch("app.api.ui_routes._get_positions_unified_reconcile_health", side_effect=_fixed_health_block), \
         patch("app.api.ui_routes._get_positions_unified_rebuild_health", side_effect=_fixed_health_block), \
         patch("app.api.ui_routes._get_positions_unified_integrity_check_health", side_effect=_fixed_health_block), \
         patch("app.api.ui_routes._get_mark_refresh_health", side_effect=_fixed_health_block), \
         patch("app.api.ui_routes._get_portfolio_risk_notifier_health", side_effect=_fixed_health_block):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r1 = client.get(
            "/api/ui/trade-ticket/readiness-pack",
            params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY", "include_paper": True},
        )
        r2 = client.get(
            "/api/ui/trade-ticket/readiness-pack",
            params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY", "include_paper": True},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    z1 = zipfile.ZipFile(BytesIO(r1.content), "r")
    z2 = zipfile.ZipFile(BytesIO(r2.content), "r")
    for name in EXPECTED_ZIP_NAMES:
        if name not in z1.namelist() or name not in z2.namelist():
            continue
        j1 = json.loads(z1.read(name).decode("utf-8"))
        j2 = json.loads(z2.read(name).decode("utf-8"))
        if name == "manifest.json":
            assert j1.get("symbol") == j2.get("symbol")
            assert j1.get("mode") == j2.get("mode")
            assert j1.get("ticket_kind") == j2.get("ticket_kind")
            assert j1.get("include_paper") == j2.get("include_paper")
            assert j1.get("included_files") == j2.get("included_files")
            assert j1.get("counts") == j2.get("counts")
        else:
            assert j1 == j2, f"{name} differed between runs"
    z1.close()
    z2.close()


def test_pack_does_not_write_decision_latest(tmp_path: Path) -> None:
    """GET trade-ticket/readiness-pack does not create or modify out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get(
            "/api/ui/trade-ticket/readiness-pack",
            params={"symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY", "include_paper": True},
        )
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
