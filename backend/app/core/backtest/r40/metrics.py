# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 research metrics — pure functions over trade lists / equity curves.

SIMULATION only. Not optimized for trade count; expectancies and risk metrics
are first-class. No live market calls.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union


@dataclass(frozen=True)
class TradeRecord:
    """Minimal trade row for R40 metrics.

    ``pnl`` is realized P&L in currency units (already sized).
    ``premium`` is credit received at entry (positive for short premium).
    ``capital`` is collateral / capital reserved for the trade when known.
    ``assigned`` marks assignment outcomes.
    ``bar_index`` optional equity-curve bar for recovery_bars (entry/exit order).
    """

    pnl: float
    premium: float = 0.0
    capital: float = 0.0
    assigned: bool = False
    bar_index: Optional[int] = None
    symbol: str = ""
    strategy: str = ""


def _as_trade(row: Union[TradeRecord, Mapping[str, Any]]) -> TradeRecord:
    if isinstance(row, TradeRecord):
        return row
    return TradeRecord(
        pnl=float(row.get("pnl") or 0.0),
        premium=float(row.get("premium") or 0.0),
        capital=float(row.get("capital") or row.get("collateral") or 0.0),
        assigned=bool(row.get("assigned") or str(row.get("outcome") or "").lower() == "assigned"),
        bar_index=int(row["bar_index"]) if row.get("bar_index") is not None else None,
        symbol=str(row.get("symbol") or ""),
        strategy=str(row.get("strategy") or ""),
    )


def trade_count(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> int:
    return len(list(trades))


def win_rate(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    rows = [_as_trade(t) for t in trades]
    if not rows:
        return None
    wins = sum(1 for t in rows if t.pnl > 0)
    return round(100.0 * wins / len(rows), 4)


def avg_win(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    wins = [t.pnl for t in (_as_trade(x) for x in trades) if t.pnl > 0]
    if not wins:
        return None
    return round(sum(wins) / len(wins), 6)


def avg_loss(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    """Average loss magnitude as a negative number (or None if no losses)."""
    losses = [t.pnl for t in (_as_trade(x) for x in trades) if t.pnl < 0]
    if not losses:
        return None
    return round(sum(losses) / len(losses), 6)


def expectancy(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    """Mean P&L per trade (currency units)."""
    rows = [_as_trade(t) for t in trades]
    if not rows:
        return None
    return round(sum(t.pnl for t in rows) / len(rows), 6)


def profit_factor(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    """Gross profit / abs(gross loss). None if no losses; inf-like capped as None when zero loss."""
    rows = [_as_trade(t) for t in trades]
    if not rows:
        return None
    gp = sum(t.pnl for t in rows if t.pnl > 0)
    gl = abs(sum(t.pnl for t in rows if t.pnl < 0))
    if gl == 0:
        # Undefined (no losses) — including infinite profit-factor cases.
        return None
    return round(gp / gl, 6)


def assignment_rate(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    rows = [_as_trade(t) for t in trades]
    if not rows:
        return None
    return round(100.0 * sum(1 for t in rows if t.assigned) / len(rows), 4)


def premium_yield(
    trades: Sequence[Union[TradeRecord, Mapping[str, Any]]],
    *,
    total_capital: Optional[float] = None,
) -> Optional[float]:
    """Total premium / capital. Uses sum(capital) when total_capital omitted."""
    rows = [_as_trade(t) for t in trades]
    if not rows:
        return None
    prem = sum(t.premium for t in rows)
    cap = float(total_capital) if total_capital is not None else sum(t.capital for t in rows)
    if cap <= 0:
        return None
    return round(prem / cap, 6)


def capital_utilization(
    trades: Sequence[Union[TradeRecord, Mapping[str, Any]]],
    *,
    account_capital: float,
    bars: int = 1,
) -> Optional[float]:
    """Average capital reserved / account_capital (0–1 scale).

    Approximation: mean(capital) / account when bars==1; else
    sum(capital) / (account_capital * bars).
    """
    rows = [_as_trade(t) for t in trades]
    if account_capital <= 0:
        return None
    if not rows:
        return 0.0
    if bars <= 1:
        mean_cap = sum(t.capital for t in rows) / len(rows)
        return round(mean_cap / account_capital, 6)
    return round(sum(t.capital for t in rows) / (account_capital * bars), 6)


def equity_curve_from_trades(
    trades: Sequence[Union[TradeRecord, Mapping[str, Any]]],
    *,
    starting_equity: float = 0.0,
) -> List[float]:
    """Cumulative P&L curve ordered by input (or bar_index when present)."""
    rows = [_as_trade(t) for t in trades]
    if any(t.bar_index is not None for t in rows):
        rows = sorted(rows, key=lambda t: (t.bar_index is None, t.bar_index if t.bar_index is not None else 0))
    curve: List[float] = []
    eq = float(starting_equity)
    for t in rows:
        eq += t.pnl
        curve.append(eq)
    return curve


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Peak-to-trough drawdown as a non-negative currency amount."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    mdd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > mdd:
            mdd = dd
    return round(mdd, 6)


def tail_loss_p95(trades: Sequence[Union[TradeRecord, Mapping[str, Any]]]) -> Optional[float]:
    """95th percentile of loss magnitude among losing trades (positive number).

    If fewer than one loss, returns None. Uses nearest-rank on sorted abs(losses).
    """
    losses = sorted(abs(t.pnl) for t in (_as_trade(x) for x in trades) if t.pnl < 0)
    if not losses:
        return None
    # nearest-rank: ceil(0.95 * n) - 1
    idx = max(0, min(len(losses) - 1, int((0.95 * len(losses) + 0.999999)) - 1))
    # clearer: percentile index
    rank = max(1, int(round(0.95 * len(losses))))
    idx = min(len(losses) - 1, rank - 1)
    return round(losses[idx], 6)


def recovery_bars(equity_curve: Sequence[float]) -> Optional[int]:
    """Bars from deepest drawdown trough back to prior peak equity.

    Returns None if never recovered (or empty). Returns 0 if no drawdown.
    """
    if len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    worst_dd = 0.0
    trough_i = 0
    for i, v in enumerate(equity_curve):
        if v > peak:
            peak = v
        dd = peak - v
        if dd > worst_dd:
            worst_dd = dd
            trough_i = i
    if worst_dd <= 0:
        return 0
    peak_before = equity_curve[0]
    for i in range(0, trough_i + 1):
        if equity_curve[i] >= peak_before:
            peak_before = equity_curve[i]
    for j in range(trough_i + 1, len(equity_curve)):
        if equity_curve[j] >= peak_before:
            return j - trough_i
    return None


@dataclass
class MetricsBundle:
    trade_count: int
    win_rate: Optional[float]
    expectancy: Optional[float]
    avg_win: Optional[float]
    avg_loss: Optional[float]
    profit_factor: Optional[float]
    max_drawdown: float
    premium_yield: Optional[float]
    capital_utilization: Optional[float]
    assignment_rate: Optional[float]
    tail_loss_p95: Optional[float]
    recovery_bars: Optional[int]
    total_pnl: float
    equity_curve: List[float] = field(default_factory=list)
    label: str = "SIMULATION"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["simulation"] = True
        return d


def compute_metrics(
    trades: Sequence[Union[TradeRecord, Mapping[str, Any]]],
    *,
    equity_curve: Optional[Sequence[float]] = None,
    account_capital: Optional[float] = None,
    bars: int = 1,
    starting_equity: float = 0.0,
) -> MetricsBundle:
    """Compute the R40 metric suite. Always labeled SIMULATION."""
    rows = [_as_trade(t) for t in trades]
    curve = list(equity_curve) if equity_curve is not None else equity_curve_from_trades(rows, starting_equity=starting_equity)
    util = None
    if account_capital is not None:
        util = capital_utilization(rows, account_capital=account_capital, bars=bars)
    return MetricsBundle(
        trade_count=trade_count(rows),
        win_rate=win_rate(rows),
        expectancy=expectancy(rows),
        avg_win=avg_win(rows),
        avg_loss=avg_loss(rows),
        profit_factor=profit_factor(rows),
        max_drawdown=max_drawdown(curve),
        premium_yield=premium_yield(rows, total_capital=account_capital),
        capital_utilization=util,
        assignment_rate=assignment_rate(rows),
        tail_loss_p95=tail_loss_p95(rows),
        recovery_bars=recovery_bars(curve),
        total_pnl=round(sum(t.pnl for t in rows), 6),
        equity_curve=curve,
        label="SIMULATION",
    )
