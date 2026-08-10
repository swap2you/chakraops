# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 walk-forward — fixture-driven, no look-ahead, SIMULATION labeled."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.backtest.r40.walk_forward import run_walk_forward, summarize_for_report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "r40"


def test_walk_forward_fixture_splits_train_oos() -> None:
    result = run_walk_forward(
        profile="balanced",
        fixture_dir=FIXTURE,
        train_start="2024-01-01",
        train_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2024-12-31",
        account_capital=150_000,
    )
    assert result.simulation is True
    assert result.manual_only is True
    assert result.label == "SIMULATION"
    assert result.source == "trades_fixture"
    assert result.train_metrics["trade_count"] == 5
    assert result.oos_metrics["trade_count"] == 5
    assert result.frozen_params["frozen_from"] == "train_window"
    # OOS entries must not include train dates
    for t in result.oos_trades:
        assert t["entry_date"] >= "2024-07-01"


def test_look_ahead_guard_rejects_overlapping_windows() -> None:
    with pytest.raises(ValueError, match="Look-ahead"):
        run_walk_forward(
            profile="balanced",
            fixture_dir=FIXTURE,
            train_start="2024-01-01",
            train_end="2024-07-15",
            oos_start="2024-07-01",
            oos_end="2024-12-31",
        )


def test_summarize_for_report_flags() -> None:
    result = run_walk_forward(
        profile="conservative",
        trades_fixture=FIXTURE / "trades.json",
        train_start="2024-01-01",
        train_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2024-12-31",
    )
    summary = summarize_for_report(result)
    assert summary["simulation"] is True
    assert summary["manual_only"] is True
    assert "oos" in summary and "metrics" in summary["oos"]
    raw = json.dumps(summary)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_empty_fixture_still_returns_simulation() -> None:
    result = run_walk_forward(
        profile="balanced",
        train_start="2024-01-01",
        train_end="2024-06-30",
        oos_start="2024-07-01",
        oos_end="2024-12-31",
    )
    assert result.source == "empty"
    assert result.oos_metrics["trade_count"] == 0
    assert result.simulation is True
