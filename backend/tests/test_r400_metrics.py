# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 metrics unit tests — pure functions, no live data."""

from __future__ import annotations

from app.core.backtest.r40.fills import FillAssumptions, premium_fill
from app.core.backtest.r40.metrics import (
    TradeRecord,
    assignment_rate,
    avg_loss,
    avg_win,
    capital_utilization,
    compute_metrics,
    equity_curve_from_trades,
    expectancy,
    max_drawdown,
    premium_yield,
    profit_factor,
    recovery_bars,
    tail_loss_p95,
    trade_count,
    win_rate,
)


def test_trade_count_and_win_rate() -> None:
    trades = [
        TradeRecord(pnl=10),
        TradeRecord(pnl=-5),
        TradeRecord(pnl=20),
    ]
    assert trade_count(trades) == 3
    assert win_rate(trades) == 66.6667


def test_expectancy_avg_win_loss_profit_factor() -> None:
    trades = [
        {"pnl": 100},
        {"pnl": 50},
        {"pnl": -25},
        {"pnl": -25},
    ]
    assert expectancy(trades) == 25.0
    assert avg_win(trades) == 75.0
    assert avg_loss(trades) == -25.0
    assert profit_factor(trades) == 3.0


def test_max_drawdown_and_recovery_bars() -> None:
    curve = [0.0, 10.0, 5.0, 2.0, 8.0, 12.0]
    assert max_drawdown(curve) == 8.0
    # Peak 10 at index 1, trough 2 at index 3, recover to >=10 at index 5 → 2 bars
    assert recovery_bars(curve) == 2


def test_premium_yield_capital_util_assignment_tail() -> None:
    trades = [
        TradeRecord(pnl=100, premium=1.0, capital=10_000, assigned=False),
        TradeRecord(pnl=-50, premium=0.5, capital=10_000, assigned=True),
        TradeRecord(pnl=-200, premium=0.8, capital=20_000, assigned=False),
        TradeRecord(pnl=20, premium=0.2, capital=5_000, assigned=False),
    ]
    assert premium_yield(trades) == round(2.5 / 45_000, 6)
    util = capital_utilization(trades, account_capital=100_000)
    assert util is not None and util > 0
    assert assignment_rate(trades) == 25.0
    # losses: 50, 200 → p95 near the larger
    assert tail_loss_p95(trades) == 200.0


def test_compute_metrics_bundle_labeled_simulation() -> None:
    trades = [TradeRecord(pnl=10, premium=1, capital=1000), TradeRecord(pnl=-5, premium=0.5, capital=1000)]
    m = compute_metrics(trades, account_capital=50_000)
    d = m.to_dict()
    assert d["simulation"] is True
    assert d["label"] == "SIMULATION"
    assert d["trade_count"] == 2
    assert d["total_pnl"] == 5.0
    assert "max_drawdown" in d
    assert "expectancy" in d


def test_equity_curve_sorts_by_bar_index() -> None:
    trades = [
        TradeRecord(pnl=10, bar_index=2),
        TradeRecord(pnl=-5, bar_index=0),
        TradeRecord(pnl=3, bar_index=1),
    ]
    curve = equity_curve_from_trades(trades)
    assert curve == [-5.0, -2.0, 8.0]


def test_premium_fill_sell_adverse_to_mid() -> None:
    out = premium_fill({"bid": 1.0, "ask": 1.2}, side="sell", assumptions=FillAssumptions(slippage_abs=0.01))
    assert out["simulation"] is True
    assert out["mid"] == 1.1
    assert out["fill_price"] == 1.09  # mid - 0.01


def test_premium_fill_half_spread() -> None:
    out = premium_fill(
        {"bid": 1.0, "ask": 1.2},
        side="sell",
        assumptions=FillAssumptions(use_half_spread=True),
    )
    # half spread = 0.1 → fill = 1.0
    assert out["fill_price"] == 1.0
