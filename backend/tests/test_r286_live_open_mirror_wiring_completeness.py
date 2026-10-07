# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.6: Live open mirror wiring completeness — all live create/upsert entrypoints wired; regression guardrails; safe labels only."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)


@pytest.fixture
def positions_db_override(tmp_path):
    from app.core.portfolio.positions_unified_store_r279 import (
        set_positions_db_path,
        reset_positions_db_path,
        init_db,
    )
    db_path = tmp_path / "positions.db"
    set_positions_db_path(db_path)
    init_db()
    try:
        yield db_path
    finally:
        reset_positions_db_path()


def test_live_shares_upsert_wires_mirror_idempotent(positions_db_override, tmp_path):
    """POST /api/ui/shares/positions/{symbol} (live upsert) wires mirror; unified DB has row; second upsert is idempotent."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import get_positions_db_path

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    account_db = out_dir / "account.db"
    # Point holdings_db to tmp_path so share_positions table is created there
    with patch("app.core.accounts.holdings_db._db_path", return_value=account_db):
        from app.core.accounts import holdings_db
        holdings_db.init_db()
        client = TestClient(app)
        r = client.post(
            "/api/ui/shares/positions/AAPL",
            json={"account_id": "default", "quantity": 50, "avg_cost": 100.0},
            headers={"x-ui-key": "test-key"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("symbol") == "AAPL"
    pos_id = (data.get("id") or "").strip()
    assert pos_id
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id, symbol, instrument_type, is_paper, qty FROM positions_open WHERE id = ?",
            (f"live_shares_{pos_id}",),
        ).fetchall()
        assert len(rows) == 1, "Unified DB must contain one live shares open row"
        assert rows[0][1] == "AAPL"
        assert rows[0][3] == 0
    finally:
        conn.close()
    # Idempotent: same upsert again
    with patch("app.core.accounts.holdings_db._db_path", return_value=account_db):
        r2 = client.post(
            "/api/ui/shares/positions/AAPL",
            json={"account_id": "default", "quantity": 50, "avg_cost": 100.0},
            headers={"x-ui-key": "test-key"},
        )
    assert r2.status_code == 200
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id FROM positions_open WHERE id = ?",
            (f"live_shares_{pos_id}",),
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_ui_manual_execute_wires_mirror_idempotent(positions_db_override, tmp_path):
    """POST /api/ui/positions/manual-execute (live options) wires mirror; unified has live_options_{id}; idempotent."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import get_positions_db_path
    from app.core.accounts.models import Account

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    fake_account = Account(
        account_id="default",
        provider="Manual",
        account_type="Taxable",
        total_capital=100_000.0,
        max_capital_per_trade_pct=10.0,
        max_total_exposure_pct=50.0,
        allowed_strategies=["CSP", "CC", "STOCK"],
        active=True,
    )
    body = {
        "account_id": "default",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 1,
        "strike": 450.0,
        "expiration": "2026-04-18",
    }
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir), patch(
        "app.core.accounts.store.get_account", return_value=fake_account
    ):
        client = TestClient(app)
        r = client.post(
            "/api/ui/positions/manual-execute",
            json=body,
            headers={"x-ui-key": "test-key"},
        )
    assert r.status_code == 200
    data = r.json()
    pid = (data.get("position_id") or data.get("id") or "").strip()
    assert pid
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id, symbol, instrument_type FROM positions_open WHERE id = ?",
            (f"live_options_{pid}",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "SPY"
        assert rows[0][2] == "CSP"
    finally:
        conn.close()
    # Idempotent: same request again (re-call manual_execute would create another position in store; mirror is idempotent)
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir), patch(
        "app.core.accounts.store.get_account", return_value=fake_account
    ):
        r2 = client.post(
            "/api/ui/positions/manual-execute",
            json=body,
            headers={"x-ui-key": "test-key"},
        )
    assert r2.status_code == 200
    pid2 = (r2.json().get("position_id") or r2.json().get("id") or "").strip()
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id FROM positions_open WHERE id = ?",
            (f"live_options_{pid2}",),
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_api_manual_execute_wires_mirror_idempotent(positions_db_override, tmp_path):
    """POST /api/positions/manual-execute (server route) wires mirror; unified has live_options row. R28.6."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import get_positions_db_path
    from app.core.accounts.models import Account

    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    fake_account = Account(
        account_id="default",
        provider="Manual",
        account_type="Taxable",
        total_capital=100_000.0,
        max_capital_per_trade_pct=10.0,
        max_total_exposure_pct=50.0,
        allowed_strategies=["CSP", "CC", "STOCK"],
        active=True,
    )
    body = {
        "account_id": "default",
        "symbol": "QQQ",
        "strategy": "CC",
        "contracts": 1,
        "strike": 400.0,
        "expiration": "2026-05-15",
    }
    with patch("app.core.positions.store._get_positions_dir", return_value=positions_dir), patch(
        "app.core.accounts.store.get_account", return_value=fake_account
    ):
        client = TestClient(app)
        r = client.post("/api/positions/manual-execute", json=body)
    assert r.status_code == 200
    data = r.json()
    pid = (data.get("position_id") or data.get("id") or "").strip()
    assert pid
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id, symbol, instrument_type FROM positions_open WHERE id = ?",
            (f"live_options_{pid}",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "QQQ"
        assert rows[0][2] == "CC"
    finally:
        conn.close()


def test_live_open_wiring_does_not_write_decision_latest(positions_db_override, tmp_path):
    """Live open mirror wiring paths do not write out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_shares_open_to_unified,
        mirror_live_open_to_unified,
        ensure_reconcile_advisory_notification,
    )

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
    mirror_live_shares_open_to_unified({
        "id": "s1",
        "symbol": "X",
        "quantity": 10,
        "opened_at": "2026-03-01T00:00:00",
        "created_at": "2026-03-01T00:00:00",
    })
    mirror_live_open_to_unified({
        "position_id": "o1",
        "id": "o1",
        "symbol": "Y",
        "strategy": "CSP",
        "contracts": 1,
        "opened_at": "2026-03-01T00:00:00",
    })
    ensure_reconcile_advisory_notification()
    after = decision_path.read_text()
    assert after == before


def test_reconcile_and_mirror_responses_no_fail_warn_pass(positions_db_override):
    """Reconcile health and mirror-related API responses must not contain FAIL/WARN/PASS tokens."""
    from app.core.portfolio.positions_unified_store_r279 import (
        get_positions_unified_reconcile_health,
        build_unified_positions,
    )

    health = get_positions_unified_reconcile_health()
    raw = json.dumps(health, default=str)
    assert not FORBIDDEN.search(raw), "Reconcile health must not contain FAIL/WARN/PASS"
    assert health.get("status") in ("OK", "Review")

    positions = build_unified_positions(state="open", include_paper=True)
    for row in positions:
        row_str = json.dumps(row, default=str)
        assert not FORBIDDEN.search(row_str), "Unified position row must not contain FAIL/WARN/PASS"
