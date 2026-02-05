# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Trade Journal: PnL math (partial exits), CSV export column stability."""

from __future__ import annotations

import csv
import io
from unittest.mock import patch

import pytest

from app.core.journal.models import Trade, Fill, FillAction
from app.core.journal.store import compute_trade_derived
from app.core.journal.export import TRADE_CSV_COLUMNS, _trade_row, export_trades_csv, export_trade_csv


# -----------------------------------------------------------------------------
# PnL and derived fields (partial exits)
# -----------------------------------------------------------------------------


def test_compute_trade_derived_partial_exits_pnl() -> None:
    """Partial exits: multiple CLOSE fills; remaining_qty, avg_exit, realized_pnl correct."""
    # Trade: 2 contracts, entry_mid_est 2.0 (sold at 2.0). Close 1 at 1.5, 1 at 1.0.
    trade = Trade(
        trade_id="test_1",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry="2026-03-21",
        strike=500.0,
        side="SELL",
        contracts=2,
        entry_mid_est=2.0,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[
            Fill("f1", "test_1", "2026-02-02T10:00:00Z", FillAction.CLOSE, 1, 1.5, 0.0, []),
            Fill("f2", "test_1", "2026-02-03T10:00:00Z", FillAction.CLOSE, 1, 1.0, 0.0, []),
        ],
    )
    compute_trade_derived(trade)

    assert trade.remaining_qty == 0
    assert trade.avg_entry == 2.0
    assert trade.avg_exit == 1.25  # (1.5 + 1.0) / 2
    # Realized: (2 - 1.5)*100*1 + (2 - 1.0)*100*1 = 50 + 100 = 150
    assert trade.realized_pnl is not None
    assert abs(trade.realized_pnl - 150.0) < 0.01


def test_compute_trade_derived_partial_exit_with_fees() -> None:
    """Partial exit with fees: fees reduce realized PnL."""
    trade = Trade(
        trade_id="test_2",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=3.0,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[
            Fill("f1", "test_2", "2026-02-02T10:00:00Z", FillAction.CLOSE, 1, 2.0, 5.0, []),
        ],
    )
    compute_trade_derived(trade)

    assert trade.remaining_qty == 0
    assert trade.avg_entry == 3.0
    assert trade.avg_exit == 2.0
    # (3 - 2) * 100 * 1 - 5 = 95
    assert trade.realized_pnl is not None
    assert abs(trade.realized_pnl - 95.0) < 0.01


def test_compute_trade_derived_open_fills_affect_avg_entry() -> None:
    """OPEN fills set avg_entry when present; remaining_qty = contracts + open - close."""
    trade = Trade(
        trade_id="test_3",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=0,
        entry_mid_est=1.5,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[
            Fill("f1", "test_3", "2026-02-01T10:00:00Z", FillAction.OPEN, 2, 1.6, 0.0, []),
            Fill("f2", "test_3", "2026-02-02T10:00:00Z", FillAction.CLOSE, 1, 1.2, 0.0, []),
        ],
    )
    compute_trade_derived(trade)

    assert trade.remaining_qty == 1  # 0 + 2 - 1
    assert trade.avg_entry == 1.6  # from OPEN fill
    assert trade.avg_exit == 1.2
    # (1.6 - 1.2) * 100 * 1 = 40
    assert trade.realized_pnl is not None
    assert abs(trade.realized_pnl - 40.0) < 0.01


# -----------------------------------------------------------------------------
# CSV export column stability
# -----------------------------------------------------------------------------


def test_csv_columns_stable_and_match_header() -> None:
    """TRADE_CSV_COLUMNS order is fixed; _trade_row length matches; export header matches."""
    assert len(TRADE_CSV_COLUMNS) == 17

    trade = Trade(
        trade_id="t1",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry="2026-03-21",
        strike=500.0,
        side="SELL",
        contracts=1,
        entry_mid_est=2.0,
        run_id=None,
        notes="x",
        stop_level=1.5,
        target_levels=[0.5, 0.25],
        fills=[],
    )
    compute_trade_derived(trade)
    row = _trade_row(trade)
    assert len(row) == len(TRADE_CSV_COLUMNS)

    # Export all (empty or with one trade) produces header exactly TRADE_CSV_COLUMNS
    with patch("app.core.journal.export.list_trades", return_value=[]):
        csv_content = export_trades_csv(limit=10)
    lines = csv_content.strip().split("\n")
    assert len(lines) >= 1
    header = next(csv.reader(io.StringIO(lines[0])))
    assert header == list(TRADE_CSV_COLUMNS)


def test_export_trade_csv_columns_stable() -> None:
    """Single-trade export CSV has same column order as TRADE_CSV_COLUMNS."""
    with patch("app.core.journal.export.get_trade") as mock_get:
        trade = Trade(
            trade_id="t2",
            symbol="QQQ",
            strategy="CC",
            opened_at="2026-02-01T10:00:00Z",
            expiry=None,
            strike=None,
            side="SELL",
            contracts=1,
            entry_mid_est=None,
            run_id=None,
            notes=None,
            stop_level=None,
            target_levels=[],
            fills=[],
        )
        compute_trade_derived(trade)
        mock_get.return_value = trade

        csv_content = export_trade_csv("t2")
        assert csv_content is not None
        lines = csv_content.strip().split("\n")
        assert len(lines) == 2  # header + one row
        header = next(csv.reader(io.StringIO(lines[0])))
        assert header == list(TRADE_CSV_COLUMNS)
