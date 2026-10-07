# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.5: Journal-driven backtest replay. Deterministic; no FAIL_/WARN_ in outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.journal.journal_store import journal_list_range


@dataclass
class BacktestResult:
    """Result of run_backtest. Safe for JSON; no FAIL_/WARN_."""
    total_realized_pl: float
    total_fees: float
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float
    by_strategy: Dict[str, Dict[str, Any]]  # strategy -> realized_pl, trades, wins, losses
    trades: List[Dict[str, Any]]  # per-trade rows
    max_drawdown_proxy: Optional[float] = None
    mode: str = "live"  # live | paper | mixed


def _float(x: Any) -> float:
    if x is None:
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def run_backtest(
    start_date: str,
    end_date: str,
    include_paper: bool = True,
    paper_only: bool = False,
) -> BacktestResult:
    """
    R27.5: Deterministic backtest from journal entries in [start_date, end_date].
    Order: trade_date ASC, created_ts ASC, id ASC.
    SHARES: BUY/SELL with cost basis; OPTIONS: OPEN/CLOSE/ROLL with premium-based P/L when realized_pl missing.
    """
    entries = journal_list_range(
        start_date.strip()[:10],
        end_date.strip()[:10],
        include_paper=include_paper,
        paper_only=paper_only,
    )
    mode = "paper" if paper_only else ("mixed" if include_paper else "live")

    # SHARES position state: symbol -> { qty, cost_total }
    positions: Dict[str, Dict[str, float]] = {}
    trades: List[Dict[str, Any]] = []
    total_realized = 0.0
    total_fees = 0.0
    win_count = 0
    loss_count = 0
    by_strategy: Dict[str, Dict[str, Any]] = {}

    def _ensure_strategy(s: str) -> None:
        s = (s or "SHARES").upper()
        if s not in by_strategy:
            by_strategy[s] = {"realized_pl": 0.0, "trades": 0, "wins": 0, "losses": 0}

    def _record_trade(row: Dict[str, Any], realized_pl: float, strategy_key: str, extra: Optional[Dict[str, Any]] = None) -> None:
        out: Dict[str, Any] = {
            "trade_date": row.get("trade_date"),
            "symbol": row.get("symbol"),
            "strategy": row.get("strategy"),
            "action": row.get("action"),
            "qty": row.get("qty"),
            "price": row.get("price"),
            "premium": row.get("premium"),
            "fees": row.get("fees"),
            "realized_pl": round(realized_pl, 2),
            "is_paper": bool(row.get("is_paper")),
            "link_id": row.get("link_id"),
            "tags": row.get("tags"),
        }
        if extra:
            out.update(extra)
        trades.append(out)
        _ensure_strategy(strategy_key)
        by_strategy[strategy_key]["realized_pl"] += realized_pl
        by_strategy[strategy_key]["trades"] += 1
        if realized_pl > 0:
            by_strategy[strategy_key]["wins"] += 1
        elif realized_pl < 0:
            by_strategy[strategy_key]["losses"] += 1

    for e in entries:
        strategy = (e.get("strategy") or "SHARES").upper()
        action = (e.get("action") or "").upper()
        qty = _float(e.get("qty"))
        price = _float(e.get("price"))
        premium = _float(e.get("premium"))
        fees = _float(e.get("fees"))
        total_fees += fees
        realized_pl = e.get("realized_pl")
        if realized_pl is not None:
            realized_pl = float(realized_pl)
        else:
            realized_pl = None

        if strategy == "SHARES":
            symbol = (e.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if symbol not in positions:
                positions[symbol] = {"qty": 0.0, "cost_total": 0.0}
            pos = positions[symbol]
            if action == "BUY":
                pos["qty"] += qty
                pos["cost_total"] += price * qty
                continue
            if action == "SELL":
                if pos["qty"] <= 0:
                    pl = 0.0
                else:
                    avg_cost = pos["cost_total"] / pos["qty"] if pos["qty"] else 0.0
                    pl = (realized_pl if realized_pl is not None else (price - avg_cost) * qty) - fees
                    pos["qty"] -= qty
                    pos["cost_total"] = max(0.0, pos["cost_total"] - avg_cost * qty)
                total_realized += pl
                if pl > 0:
                    win_count += 1
                elif pl < 0:
                    loss_count += 1
                _record_trade(e, pl, strategy)
            continue

        # OPTIONS: CSP, CC
        if action in ("OPEN_CSP", "OPEN_CC", "OPEN"):
            pl = realized_pl if realized_pl is not None else (premium * 100 * qty - fees)
            total_realized += pl
            if pl > 0:
                win_count += 1
            elif pl < 0:
                loss_count += 1
            _record_trade(e, pl, strategy)
            continue
        if action in ("CLOSE_CSP", "CLOSE_CC", "CLOSE"):
            pl = realized_pl if realized_pl is not None else (-premium * 100 * qty - fees)
            total_realized += pl
            if pl > 0:
                win_count += 1
            elif pl < 0:
                loss_count += 1
            _record_trade(e, pl, strategy)
            continue
        if action == "ROLL":
            pl = realized_pl if realized_pl is not None else 0.0
            total_realized += pl
            if pl > 0:
                win_count += 1
            elif pl < 0:
                loss_count += 1
            extra = {"incomplete_roll": True} if realized_pl is None else None
            _record_trade(e, pl, strategy, extra=extra)
            continue

    trade_count = len(trades)
    win_rate = (win_count / trade_count * 100.0) if trade_count else 0.0

    # Round by_strategy for JSON
    for k, v in by_strategy.items():
        v["realized_pl"] = round(v["realized_pl"], 2)

    # Max drawdown proxy: cumulative curve then max peak-to-trough
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += _float(t.get("realized_pl"))
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    max_drawdown_proxy = abs(max_dd) if max_dd != 0 else None

    return BacktestResult(
        total_realized_pl=round(total_realized, 2),
        total_fees=round(total_fees, 2),
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=round(win_rate, 2),
        by_strategy=by_strategy,
        trades=trades,
        max_drawdown_proxy=round(max_drawdown_proxy, 2) if max_drawdown_proxy is not None else None,
        mode=mode,
    )
