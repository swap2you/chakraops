# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Phase 6.4: capital ledger and monthly outcome accounting."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.capital_ledger import CapitalLedgerEventType, CapitalLedgerEntry, MonthlySummary
from app.core.persistence import (
    add_capital_ledger_entry,
    compute_monthly_summary,
    get_capital_ledger_entries,
    get_capital_deployed_today,
    get_mtd_realized_pnl,
    init_persistence_db,
    record_trade,
    upsert_position_from_trade,
)


@pytest.fixture
def temp_db():
    """Use a temporary database so ledger tests don't mix with shared DB."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        from app.db import database
        from app.core import persistence
        orig_db = database.get_db_path
        database.get_db_path = lambda: db_path
        persistence.get_db_path = lambda: db_path
        init_persistence_db()
        yield db_path
    finally:
        database.get_db_path = orig_db
        persistence.get_db_path = orig_db
        if db_path.exists():
            db_path.unlink(missing_ok=True)


def test_ledger_entry_model():
    """CapitalLedgerEntry has date, position_id, event_type, cash_delta, notes."""
    e = CapitalLedgerEntry(
        date="2026-02-01",
        position_id="pos-1",
        event_type=CapitalLedgerEventType.OPEN.value,
        cash_delta=250.0,
        notes="test",
    )
    assert e.date == "2026-02-01"
    assert e.position_id == "pos-1"
    assert e.event_type == "OPEN"
    assert e.cash_delta == 250.0
    assert e.notes == "test"


def test_ledger_balances_match_position_events():
    """Ledger entries sum correctly: OPEN credit + PARTIAL_CLOSE/CLOSE = capital truth."""
    init_persistence_db()
    pid = f"test-ledger-bal-{uuid.uuid4().hex[:12]}"
    add_capital_ledger_entry("2026-02-01", pid, "OPEN", 300.0, "open")
    add_capital_ledger_entry("2026-02-15", pid, "PARTIAL_CLOSE", 50.0, "partial")
    add_capital_ledger_entry("2026-02-20", pid, "CLOSE", 80.0, "close")
    entries = get_capital_ledger_entries(position_id=pid)
    assert len(entries) == 3
    total_open = sum(e["cash_delta"] for e in entries if e["event_type"] == "OPEN")
    total_realized = sum(
        e["cash_delta"] for e in entries if e["event_type"] in ("PARTIAL_CLOSE", "CLOSE")
    )
    assert total_open == 300.0
    assert total_realized == 130.0
    assert total_open + total_realized == 430.0  # credit + realized (simplified view)


def test_monthly_summary_deterministic(temp_db):
    """Same inputs -> same monthly numbers (reproducible)."""
    pid = f"test-mtd-{uuid.uuid4().hex[:12]}"
    add_capital_ledger_entry("2099-11-01", pid, "OPEN", 100.0)
    add_capital_ledger_entry("2099-11-10", pid, "CLOSE", 15.0)
    s1 = compute_monthly_summary(2099, 11)
    s2 = compute_monthly_summary(2099, 11)
    assert s1.year == s2.year == 2099
    assert s1.month == s2.month == 11
    assert s1.total_credit_collected == s2.total_credit_collected == 100.0
    assert s1.realized_pnl == s2.realized_pnl == 15.0
    assert s1.win_rate == s2.win_rate
    assert s1.avg_days_in_trade == s2.avg_days_in_trade
    assert s1.max_drawdown == s2.max_drawdown


def test_partial_closes_handled_correctly(temp_db):
    """PARTIAL_CLOSE entries contribute to realized_pnl in monthly summary."""
    pid = f"test-partial-{uuid.uuid4().hex[:12]}"
    add_capital_ledger_entry("2099-12-01", pid, "OPEN", 200.0)
    add_capital_ledger_entry("2099-12-15", pid, "PARTIAL_CLOSE", 30.0)
    add_capital_ledger_entry("2099-12-25", pid, "CLOSE", 40.0)
    summary = compute_monthly_summary(2099, 12)
    assert summary.total_credit_collected == 200.0
    assert summary.realized_pnl == 70.0  # 30 + 40
    assert summary.year == 2099
    assert summary.month == 12


def test_get_ledger_entries_filter_by_date():
    """get_capital_ledger_entries filters by date_from and date_to."""
    init_persistence_db()
    pid = f"test-date-{uuid.uuid4().hex[:12]}"
    add_capital_ledger_entry("2026-05-01", pid, "OPEN", 50.0)
    add_capital_ledger_entry("2026-05-15", pid, "CLOSE", 10.0)
    add_capital_ledger_entry("2026-06-01", pid + "x", "OPEN", 60.0)
    feb = get_capital_ledger_entries(date_from="2026-02-01", date_to="2026-02-28")
    may = get_capital_ledger_entries(date_from="2026-05-01", date_to="2026-05-31")
    assert len(may) >= 2
    may_open = [e for e in may if e["event_type"] == "OPEN" and e["position_id"] == pid]
    assert len(may_open) == 1
    assert may_open[0]["cash_delta"] == 50.0


def test_monthly_summary_empty_month():
    """compute_monthly_summary for month with no entries returns zeros."""
    summary = compute_monthly_summary(2099, 1)
    assert summary.year == 2099
    assert summary.month == 1
    assert summary.total_credit_collected == 0.0
    assert summary.realized_pnl == 0.0
    assert summary.win_rate == 0.0
    assert summary.avg_days_in_trade == 0.0
    assert summary.max_drawdown == 0.0


def test_capital_deployed_today_and_mtd():
    """get_capital_deployed_today and get_mtd_realized_pnl return numbers (smoke)."""
    init_persistence_db()
    deployed = get_capital_deployed_today()
    mtd = get_mtd_realized_pnl()
    assert isinstance(deployed, (int, float))
    assert isinstance(mtd, (int, float))


def test_monthly_summary_dataclass():
    """MonthlySummary has all required fields and types."""
    s = MonthlySummary(
        year=2026,
        month=2,
        total_credit_collected=500.0,
        realized_pnl=75.0,
        unrealized_pnl=0.0,
        win_rate=0.6,
        avg_days_in_trade=12.5,
        max_drawdown=50.0,
    )
    assert s.year == 2026
    assert s.month == 2
    assert s.total_credit_collected == 500.0
    assert s.realized_pnl == 75.0
    assert s.win_rate == 0.6
    assert s.avg_days_in_trade == 12.5
    assert s.max_drawdown == 50.0


def test_ledger_reconciles_with_positions(temp_db):
    """Ledger OPEN/CLOSE entries match position lifecycle (record_trade + upsert)."""
    # SELL_TO_OPEN -> position + OPEN ledger entry
    t1 = record_trade(
        symbol="RECON",
        action="SELL_TO_OPEN",
        strike=100.0,
        expiry="2099-06-20",
        contracts=1,
        premium=150.0,
        notes="recon test",
    )
    pos = upsert_position_from_trade(t1)
    assert pos is not None
    assert pos.premium_collected == 150.0
    entries_open = get_capital_ledger_entries(position_id=pos.id)
    open_entries = [e for e in entries_open if e["event_type"] == "OPEN"]
    assert len(open_entries) == 1
    assert open_entries[0]["cash_delta"] == 150.0
    # BUY_TO_CLOSE -> position closed + CLOSE ledger entry (realized pnl)
    t2 = record_trade(
        symbol="RECON",
        action="BUY_TO_CLOSE",
        strike=100.0,
        expiry="2099-06-20",
        contracts=1,
        premium=-120.0,  # debit to close
        notes="close",
    )
    pos2 = upsert_position_from_trade(t2)
    assert pos2 is not None
    assert getattr(pos2, "realized_pnl", None) == 30.0  # 150 - 120
    entries_all = get_capital_ledger_entries(position_id=pos.id)
    close_entries = [e for e in entries_all if e["event_type"] == "CLOSE"]
    assert len(close_entries) == 1
    assert close_entries[0]["cash_delta"] == 30.0
