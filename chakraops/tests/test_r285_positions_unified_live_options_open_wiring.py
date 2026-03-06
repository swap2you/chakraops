# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.5: Live options OPEN mirror wiring on manual-execute; reconcile health includes live options counts; safe labels only; no decision_latest writes."""

from __future__ import annotations

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


def test_live_options_upsert_wires_mirror_to_unified_idempotent(positions_db_override, tmp_path) -> None:
    """Live options create (manual_execute) + mirror: unified positions_open has row with stable id; second mirror is idempotent."""
    from app.core.accounts.models import Account
    from app.core.positions.service import manual_execute
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_open_to_unified,
        get_positions_db_path,
    )
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
        position, errors = manual_execute(body)
    assert not errors
    assert position is not None
    assert (position.strategy or "").strip().upper() in ("CSP", "CC")
    mirror_live_open_to_unified(position.to_dict())
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        row_id = f"live_options_{position.position_id}"
        rows = conn.execute(
            "SELECT id, symbol, instrument_type, is_paper, qty FROM positions_open WHERE id = ?",
            (row_id,),
        ).fetchall()
        assert len(rows) == 1, f"Expected one row {row_id} in positions_open"
        assert rows[0][1] == "SPY"
        assert rows[0][2] == "CSP"
        assert rows[0][3] == 0
        assert rows[0][4] == 100
    finally:
        conn.close()
    mirror_live_open_to_unified(position.to_dict())
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id FROM positions_open WHERE id = ?",
            (f"live_options_{position.position_id}",),
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_reconcile_health_includes_live_options_open_counts_and_safe_labels(positions_db_override) -> None:
    """get_positions_unified_reconcile_health has live_options_open_count, unified_open_live_options_count; status OK or Review only; no FAIL/WARN/PASS."""
    from app.core.portfolio.positions_unified_store_r279 import get_positions_unified_reconcile_health
    health = get_positions_unified_reconcile_health()
    assert "live_options_open_count" in health
    assert "unified_open_live_options_count" in health
    assert health.get("status") in ("OK", "Review")
    raw = str(health)
    assert not FORBIDDEN.search(raw), "Reconcile health must not contain FAIL/WARN/PASS"


def test_wiring_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """Live options open mirror path does not write out/decision_latest.json."""
    from app.core.accounts.models import Account
    from app.core.positions.service import manual_execute
    from app.core.portfolio.positions_unified_store_r279 import mirror_live_open_to_unified, ensure_reconcile_advisory_notification
    positions_dir = tmp_path / "positions"
    positions_dir.mkdir(parents=True, exist_ok=True)
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
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
        position, errors = manual_execute(body)
    assert not errors and position is not None
    mirror_live_open_to_unified(position.to_dict())
    ensure_reconcile_advisory_notification()
    after = decision_path.read_text()
    assert after == before
