# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 9: Position-Aware Evaluation & Exposure Control.

Evaluator loads open trades from journal. Rules:
- If open CSP exists for symbol: do NOT recommend new CSP (POSITION_ALREADY_OPEN).
- If open CC exists: do NOT suggest second CC (POSITION_ALREADY_OPEN).
- Exposure limits: max capital per ticker (configurable), max concurrent positions (global).
Exposure summary is persisted into evaluation run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Lazy import journal to avoid circular deps
def _get_open_trades():
    from app.core.journal.store import list_trades
    trades = list_trades(limit=500)
    return [t for t in trades if getattr(t, "remaining_qty", 0) > 0]


def get_open_positions_by_symbol() -> Dict[str, List[Any]]:
    """
    Return open trades (remaining_qty > 0) grouped by symbol.
    Keys are normalized uppercase symbols; values are list of Trade-like objects
    with .symbol, .strategy, .remaining_qty.
    """
    by_symbol: Dict[str, List[Any]] = {}
    for t in _get_open_trades():
        sym = (getattr(t, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        by_symbol.setdefault(sym, []).append(t)
    return by_symbol


def has_open_csp(symbol: str, open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None) -> bool:
    """True if symbol has an open CSP position (remaining_qty > 0)."""
    if open_trades_by_symbol is None:
        open_trades_by_symbol = get_open_positions_by_symbol()
    sym = (symbol or "").strip().upper()
    for t in open_trades_by_symbol.get(sym, []):
        if (getattr(t, "strategy", "") or "").upper() == "CSP":
            return True
    return False


def has_open_cc(symbol: str, open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None) -> bool:
    """True if symbol has an open CC position (remaining_qty > 0)."""
    if open_trades_by_symbol is None:
        open_trades_by_symbol = get_open_positions_by_symbol()
    sym = (symbol or "").strip().upper()
    for t in open_trades_by_symbol.get(sym, []):
        if (getattr(t, "strategy", "") or "").upper() == "CC":
            return True
    return False


def position_blocks_new_csp(symbol: str, open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None) -> bool:
    """If open CSP exists for symbol, do not recommend new CSP."""
    return has_open_csp(symbol, open_trades_by_symbol)


def position_blocks_new_cc(symbol: str, open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None) -> bool:
    """If open CC exists for symbol, do not suggest second CC."""
    return has_open_cc(symbol, open_trades_by_symbol)


def position_blocks_recommendation(
    symbol: str,
    open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None,
    strategy_focus: str = "CSP",
) -> Tuple[bool, str]:
    """
    Returns (blocks, reason).
    For CSP-focused evaluation: block if open CSP or open CC (no second CC).
    """
    if open_trades_by_symbol is None:
        open_trades_by_symbol = get_open_positions_by_symbol()
    sym = (symbol or "").strip().upper()
    if strategy_focus.upper() == "CSP":
        if has_open_csp(symbol, open_trades_by_symbol):
            return True, "POSITION_ALREADY_OPEN"
        if has_open_cc(symbol, open_trades_by_symbol):
            return True, "POSITION_ALREADY_OPEN"
    else:
        if has_open_cc(symbol, open_trades_by_symbol):
            return True, "POSITION_ALREADY_OPEN"
        if has_open_csp(symbol, open_trades_by_symbol):
            return True, "POSITION_ALREADY_OPEN"
    return False, ""


@dataclass
class ExposureSummary:
    """Summary of open positions for persistence in evaluation run."""
    total_positions: int = 0
    by_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    max_concurrent_positions: int = 0
    max_capital_per_ticker_pct: float = 0.0
    at_cap: bool = False  # True if total_positions >= max_concurrent_positions
    symbols_over_capital_cap: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_positions": self.total_positions,
            "by_symbol": dict(self.by_symbol),
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_capital_per_ticker_pct": self.max_capital_per_ticker_pct,
            "at_cap": self.at_cap,
            "symbols_over_capital_cap": list(self.symbols_over_capital_cap),
        }


def get_exposure_summary(
    open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None,
    portfolio_config: Optional[Dict[str, Any]] = None,
) -> ExposureSummary:
    """
    Build exposure summary from open journal trades.
    Uses portfolio_config for max_active_positions and optional max_capital_per_ticker_pct.
    """
    if open_trades_by_symbol is None:
        open_trades_by_symbol = get_open_positions_by_symbol()
    try:
        from app.core.settings import get_portfolio_config
        config = portfolio_config or get_portfolio_config()
    except Exception:
        config = {}
    max_concurrent = int(config.get("max_active_positions", 5))
    max_capital_pct = float(config.get("max_capital_per_ticker_pct", 0.05))

    total = 0
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for sym, trades in open_trades_by_symbol.items():
        count = sum(getattr(t, "remaining_qty", 0) for t in trades)
        strategies = list({(getattr(t, "strategy", "") or "").upper() for t in trades})
        total += 1  # count distinct symbols as positions
        by_symbol[sym] = {
            "position_count": len(trades),
            "remaining_contracts": sum(getattr(t, "remaining_qty", 0) for t in trades),
            "strategies": strategies,
        }
    total_positions = len(by_symbol)  # distinct symbols with open positions
    at_cap = total_positions >= max_concurrent if max_concurrent else False
    # Symbols over capital cap would need notional per symbol; leave empty unless we add price data
    symbols_over_capital_cap: List[str] = []

    return ExposureSummary(
        total_positions=total_positions,
        by_symbol=by_symbol,
        max_concurrent_positions=max_concurrent,
        max_capital_per_ticker_pct=max_capital_pct,
        at_cap=at_cap,
        symbols_over_capital_cap=symbols_over_capital_cap,
    )


def check_exposure_limits(
    symbol: str,
    exposure_summary: ExposureSummary,
    open_trades_by_symbol: Optional[Dict[str, List[Any]]] = None,
) -> Tuple[bool, str]:
    """
    Returns (allowed, reason). If at global cap and symbol has no position, not allowed.
    If symbol already has a position, we still allow evaluation but position_blocks will handle.
    """
    if exposure_summary.at_cap:
        sym = (symbol or "").strip().upper()
        if sym not in exposure_summary.by_symbol:
            return False, "EXPOSURE_CAP"
    if symbol in exposure_summary.symbols_over_capital_cap:
        return False, "CAPITAL_PER_TICKER_CAP"
    return True, ""
