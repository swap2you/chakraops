# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 5 backtest engine (no live data, deterministic)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    SnapshotCSVDataSource,
    Trade,
    BacktestReport,
    _stock_eligible,
)


def test_stock_eligible_rejects_missing_price():
    assert _stock_eligible(None, 2_000_000, 25, "RISK_ON") is False
    assert _stock_eligible(0, 2_000_000, 25, "RISK_ON") is False


def test_stock_eligible_rejects_risk_off():
    assert _stock_eligible(100.0, 2_000_000, 25, "RISK_OFF") is False
    assert _stock_eligible(100.0, 2_000_000, 25, "UNKNOWN") is False


def test_stock_eligible_rejects_low_volume():
    assert _stock_eligible(100.0, 500_000, 25, "RISK_ON") is False


def test_stock_eligible_rejects_low_iv_rank():
    assert _stock_eligible(100.0, 2_000_000, 10, "RISK_ON") is False


def test_stock_eligible_accepts_valid():
    assert _stock_eligible(100.0, 2_000_000, 25, "RISK_ON") is True


def test_snapshot_csv_data_source_list_dates(tmp_path):
    (tmp_path / "2026-01-01.csv").write_text("symbol,price,volume,iv_rank,timestamp\nAAPL,100,1e6,20,2026-01-01T10:00:00\n")
    (tmp_path / "2026-01-03.csv").write_text("symbol,price,volume,iv_rank,timestamp\nAAPL,101,1e6,21,2026-01-03T10:00:00\n")
    ds = SnapshotCSVDataSource(tmp_path)
    dates = ds.list_dates()
    assert dates == [date(2026, 1, 1), date(2026, 1, 3)]


def test_snapshot_csv_data_source_get_snapshot(tmp_path):
    (tmp_path / "2026-01-01.csv").write_text("symbol,price,volume,iv_rank,timestamp\nSPY,450,38000000,22,2026-01-01T10:00:00\n")
    ds = SnapshotCSVDataSource(tmp_path)
    snap = ds.get_snapshot(date(2026, 1, 1))
    assert "SPY" in snap
    assert snap["SPY"]["price"] == 450
    assert snap["SPY"]["volume"] == 38000000
    assert snap["SPY"]["iv_rank"] == 22


def test_backtest_engine_run_deterministic(tmp_path):
    """Run backtest on synthetic fixtures; same inputs -> same outputs."""
    for i in range(3):
        d = date(2026, 1, 1) + timedelta(days=i)
        path = tmp_path / f"{d.isoformat()}.csv"
        path.write_text(
            "symbol,price,volume,iv_rank,timestamp\n"
            "SPY,450,38000000,22,2026-01-01T10:00:00\n"
            "AAPL,185,25000000,18,2026-01-01T10:00:00\n"
        )
    ds = SnapshotCSVDataSource(tmp_path)
    out = tmp_path / "out"
    cfg = BacktestConfig(data_source=ds, output_dir=out)
    eng = BacktestEngine(cfg)
    r1 = eng.run(cfg)
    r2 = eng.run(cfg)
    assert r1.run_id != r2.run_id  # run_ids differ
    assert r1.total_trades == r2.total_trades
    assert r1.total_pnl == r2.total_pnl
    assert (out / r1.run_id / "backtest_report.json").exists()
    assert (out / r1.run_id / "backtest_trades.csv").exists()


def test_trade_dataclass_fields():
    t = Trade(
        strategy="CSP",
        symbol="SPY",
        entry_date=date(2026, 1, 1),
        exit_date=date(2026, 2, 5),
        entry_premium=4.5,
        exit_premium_or_assignment=0.0,
        strike=445.0,
        expiry=date(2026, 2, 5),
        contracts=1,
        outcome="expired_otm",
        pnl=450.0,
    )
    assert t.symbol == "SPY"
    assert t.outcome == "expired_otm"
    assert t.pnl == 450.0
