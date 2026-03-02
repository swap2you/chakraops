# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.9: Portfolio guardrails + sizing caps (advisory-first, no gambling).

Request-time, deterministic. Hard caps block ENTRY with safe reason codes;
sector exposure is advisory only. No FAIL_/WARN_ in outputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Safe status labels only (never FAIL/WARN)
STATUS_OK = "OK"
STATUS_ADVISORY = "Advisory"
STATUS_BLOCKED = "Blocked"

# Safe reason codes for hard blocks (deterministic ordering)
REASON_CASH_RESERVE = "Cash reserve rule"
REASON_MAX_OPEN_OPTIONS = "Max open options positions reached"
REASON_MAX_OPEN_SHARES = "Max open shares positions reached"
REASON_MAX_SYMBOLS = "Max symbols exposure reached"
REASON_MAX_NOTIONAL_SYMBOL = "Max notional per symbol exceeded"
REASON_OPTIONS_RISK_PCT = "Options risk per trade cap"

# Advisory only (do not block)
REASON_SECTOR_ADVISORY = "Sector exposure advisory"


def build_guardrails_snapshot() -> Dict[str, Any]:
    """Build a snapshot from account, holdings, share_positions, and tracked option positions.
    Used as input to compute_portfolio_metrics. All data from holdings_db + positions service.
    """
    out: Dict[str, Any] = {
        "cash": 0.0,
        "total_capital": None,
        "holdings": [],
        "share_positions": [],
        "option_positions": [],
        "symbol_prices": {},
    }
    try:
        from app.core.accounts.holdings_db import (
            get_account_summary,
            list_holdings,
            list_share_positions,
            _DEFAULT_ACCOUNT_ID,
        )
        summary = get_account_summary()
        out["cash"] = float(summary.get("cash") or 0)
        out["total_capital"] = summary.get("total_capital")
        for h in list_holdings():
            out["holdings"].append({
                "symbol": (h.get("symbol") or "").strip().upper(),
                "shares": int(h.get("shares") or 0),
                "avg_cost": float(h["avg_cost"]) if h.get("avg_cost") is not None else None,
            })
        for sp in list_share_positions(_DEFAULT_ACCOUNT_ID):
            sym = (sp.get("symbol") or "").strip().upper()
            qty = int(sp.get("quantity") or 0)
            if sym and qty > 0:
                out["share_positions"].append({
                    "symbol": sym,
                    "quantity": qty,
                    "avg_cost": float(sp["avg_cost"]) if sp.get("avg_cost") is not None else None,
                })
    except Exception:
        pass
    try:
        from app.core.positions.service import list_positions
        positions = list_positions(status="OPEN", symbol=None, exclude_test=True)
        for p in positions:
            strat = (getattr(p, "strategy", "") or "").strip().upper()
            if strat in ("CSP", "CC"):
                sym = (getattr(p, "symbol", "") or "").strip().upper()
                if sym:
                    contracts = int(getattr(p, "contracts", 0) or 0)
                    strike = getattr(p, "strike", None)
                    out["option_positions"].append({
                        "symbol": sym,
                        "strategy": strat,
                        "contracts": contracts,
                        "strike": float(strike) if strike is not None else None,
                    })
    except Exception:
        pass
    return out


def compute_portfolio_metrics(
    snapshot: Dict[str, Any],
    symbol_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Compute portfolio metrics for guardrails. Deterministic.

    Returns dict with:
      open_options_count, open_shares_count, symbols_exposure_count,
      total_equity, cash_reserve_pct, max_symbol_notional_pct,
      symbol_notionals (symbol -> notional), sector_exposure_pct (if computable).
    """
    prices = dict(symbol_prices or snapshot.get("symbol_prices") or {})
    cash = float(snapshot.get("cash") or 0)
    total_capital = snapshot.get("total_capital")
    holdings = snapshot.get("holdings") or []
    share_positions = snapshot.get("share_positions") or []
    option_positions = snapshot.get("option_positions") or []

    open_options_count = len(option_positions)
    open_shares_count = len(share_positions)

    # Unique symbols with any exposure (holdings + share_positions + option_positions)
    symbols_set: set = set()
    for h in holdings:
        if (h.get("symbol") or "").strip() and int(h.get("shares") or 0) > 0:
            symbols_set.add((h.get("symbol") or "").strip().upper())
    for sp in share_positions:
        if (sp.get("symbol") or "").strip():
            symbols_set.add((sp.get("symbol") or "").strip().upper())
    for op in option_positions:
        if (op.get("symbol") or "").strip():
            symbols_set.add((op.get("symbol") or "").strip().upper())
    symbols_exposure_count = len(symbols_set)

    # Notional per symbol: shares (qty * price or avg_cost) + options (contracts * 100 * strike as proxy)
    symbol_notionals: Dict[str, float] = {}
    def add_notional(sym: str, value: float) -> None:
        if not sym:
            return
        sym = sym.strip().upper()
        symbol_notionals[sym] = symbol_notionals.get(sym, 0) + value

    for h in holdings:
        sym = (h.get("symbol") or "").strip().upper()
        shares = int(h.get("shares") or 0)
        if not sym or shares <= 0:
            continue
        price = prices.get(sym)
        if price is None and h.get("avg_cost") is not None:
            price = float(h["avg_cost"])
        if price is not None:
            add_notional(sym, shares * float(price))

    for sp in share_positions:
        sym = (sp.get("symbol") or "").strip().upper()
        qty = int(sp.get("quantity") or 0)
        if not sym or qty <= 0:
            continue
        price = prices.get(sym)
        if price is None and sp.get("avg_cost") is not None:
            price = float(sp["avg_cost"])
        if price is not None:
            add_notional(sym, qty * float(price))

    for op in option_positions:
        sym = (op.get("symbol") or "").strip().upper()
        contracts = int(op.get("contracts") or 0)
        strike = op.get("strike")
        if not sym or contracts <= 0:
            continue
        # Proxy notional: 100 * contracts * strike (or underlying price if we had it)
        underlying = prices.get(sym)
        if strike is not None:
            notional = 100 * contracts * float(strike)
        elif underlying is not None:
            notional = 100 * contracts * float(underlying)
        else:
            notional = 0.0
        if notional > 0:
            add_notional(sym, notional)

    # Total equity: prefer total_capital; else cash + sum(holdings + share_positions notional)
    if total_capital is not None:
        try:
            total_equity = float(total_capital)
        except (TypeError, ValueError):
            total_equity = cash
            for sym, n in symbol_notionals.items():
                total_equity += n
    else:
        total_equity = cash
        for sym, n in symbol_notionals.items():
            total_equity += n
    if total_equity <= 0:
        total_equity = 1.0  # avoid div by zero

    cash_reserve_pct = 100.0 * cash / total_equity if total_equity else 0.0
    max_symbol_notional_pct = 0.0
    if symbol_notionals and total_equity > 0:
        max_notional = max(symbol_notionals.values())
        max_symbol_notional_pct = 100.0 * max_notional / total_equity

    # Sector exposure: advisory only; we don't have sector map in this module, so leave None or 0
    sector_exposure_pct: Optional[float] = None

    return {
        "open_options_count": open_options_count,
        "open_shares_count": open_shares_count,
        "symbols_exposure_count": symbols_exposure_count,
        "total_equity": total_equity,
        "cash_reserve_pct": cash_reserve_pct,
        "max_symbol_notional_pct": max_symbol_notional_pct,
        "symbol_notionals": symbol_notionals,
        "sector_exposure_pct": sector_exposure_pct,
    }


def evaluate_guardrails_for_entry(
    metrics: Dict[str, Any],
    proposed_entry: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether a proposed ENTRY (options or shares) is allowed by guardrails.
    Returns {status: OK|Advisory|Blocked, hard_blocks: [...], advisories: [...]}.
    Reason codes use safe labels only; deterministic ordering.
    """
    from app.core.settings import get_guardrails_config
    cfg = config or get_guardrails_config()
    max_options = int(cfg.get("MAX_OPEN_OPTIONS_POSITIONS", 6))
    max_shares = int(cfg.get("MAX_OPEN_SHARES_POSITIONS", 10))
    max_symbols = int(cfg.get("MAX_SYMBOLS_EXPOSURE", 12))
    max_notional_pct = float(cfg.get("MAX_NOTIONAL_PER_SYMBOL_PCT", 15.0))
    min_cash_pct = float(cfg.get("MIN_CASH_RESERVE_PCT", 25.0))
    options_risk_pct = float(cfg.get("OPTIONS_MAX_RISK_PER_TRADE_PCT", 2.0))
    sector_advisory_pct = float(cfg.get("SECTOR_EXPOSURE_ADVISORY_PCT", 35.0))

    hard_blocks: List[str] = []
    advisories: List[str] = []

    strategy = (proposed_entry.get("strategy") or proposed_entry.get("side") or "OPTIONS").strip().upper()
    is_options = strategy == "OPTIONS"
    symbol = (proposed_entry.get("symbol") or "").strip().upper()

    open_options = int(metrics.get("open_options_count") or 0)
    open_shares = int(metrics.get("open_shares_count") or 0)
    symbols_count = int(metrics.get("symbols_exposure_count") or 0)
    cash_reserve_pct = float(metrics.get("cash_reserve_pct") or 0)
    max_symbol_notional_pct = float(metrics.get("max_symbol_notional_pct") or 0)
    symbol_notionals = metrics.get("symbol_notionals") or {}
    total_equity = float(metrics.get("total_equity") or 1)
    sector_pct = metrics.get("sector_exposure_pct")

    # Would adding this entry violate limits? (we check current state; for "new" symbol we add 1 to symbols_count)
    would_add_option = is_options
    would_add_share = not is_options
    new_symbol = symbol and symbol not in symbol_notionals

    # Hard blocks (deterministic order: cash, options count, shares count, symbols, notional, options risk)
    if cash_reserve_pct < min_cash_pct:
        hard_blocks.append(REASON_CASH_RESERVE)

    if would_add_option and open_options >= max_options:
        hard_blocks.append(REASON_MAX_OPEN_OPTIONS)

    if would_add_share and open_shares >= max_shares:
        hard_blocks.append(REASON_MAX_OPEN_SHARES)

    next_symbols = symbols_count + (1 if new_symbol else 0)
    if next_symbols > max_symbols:
        hard_blocks.append(REASON_MAX_SYMBOLS)

    # Max notional per symbol: block if proposed symbol's current notional is already at/over limit
    if symbol and total_equity > 0:
        sym_notional = symbol_notionals.get(symbol, 0) or 0
        sym_pct = 100.0 * float(sym_notional) / total_equity
        if sym_pct >= max_notional_pct:
            hard_blocks.append(REASON_MAX_NOTIONAL_SYMBOL)

    # Options risk per trade: if proposed_entry has risk_pct and it exceeds cap, block
    proposed_risk_pct = proposed_entry.get("risk_pct") or proposed_entry.get("options_risk_pct")
    if is_options and proposed_risk_pct is not None:
        try:
            r = float(proposed_risk_pct)
            if r > options_risk_pct:
                hard_blocks.append(REASON_OPTIONS_RISK_PCT)
        except (TypeError, ValueError):
            pass

    # Advisory only: sector exposure (do not block)
    if sector_pct is not None and sector_pct >= sector_advisory_pct:
        advisories.append(REASON_SECTOR_ADVISORY)

    status = STATUS_OK
    if hard_blocks:
        status = STATUS_BLOCKED
    elif advisories:
        status = STATUS_ADVISORY

    return {
        "status": status,
        "hard_blocks": sorted(hard_blocks),
        "advisories": sorted(advisories),
    }


def get_guardrails_metrics_and_status(
    snapshot: Optional[Dict[str, Any]] = None,
    symbol_prices: Optional[Dict[str, float]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    One-shot: build snapshot (if not provided), compute metrics, and return
    status + metrics + limits for Dashboard / System Diagnostics.
    Safe labels only; no FAIL/WARN.
    """
    from app.core.settings import get_guardrails_config
    cfg = config or get_guardrails_config()
    snap = snapshot if snapshot is not None else build_guardrails_snapshot()
    metrics = compute_portfolio_metrics(snap, symbol_prices=symbol_prices)
    # Overall status: Blocked if any hard limit is currently violated; else Advisory if any advisory; else OK
    open_options = int(metrics.get("open_options_count") or 0)
    open_shares = int(metrics.get("open_shares_count") or 0)
    symbols_count = int(metrics.get("symbols_exposure_count") or 0)
    cash_reserve_pct = float(metrics.get("cash_reserve_pct") or 0)
    max_symbol_notional_pct = float(metrics.get("max_symbol_notional_pct") or 0)
    max_options = int(cfg.get("MAX_OPEN_OPTIONS_POSITIONS", 6))
    max_shares = int(cfg.get("MAX_OPEN_SHARES_POSITIONS", 10))
    max_symbols = int(cfg.get("MAX_SYMBOLS_EXPOSURE", 12))
    max_notional_pct = float(cfg.get("MAX_NOTIONAL_PER_SYMBOL_PCT", 15.0))
    min_cash_pct = float(cfg.get("MIN_CASH_RESERVE_PCT", 25.0))

    blocked = False
    if cash_reserve_pct < min_cash_pct:
        blocked = True
    if open_options >= max_options:
        blocked = True
    if open_shares >= max_shares:
        blocked = True
    if symbols_count >= max_symbols:
        blocked = True
    if max_symbol_notional_pct >= max_notional_pct:
        blocked = True

    status = STATUS_BLOCKED if blocked else STATUS_OK
    # R26.0: Available budget for sizing (post cash reserve)
    available_budget_usd: float = 0.0
    cash_secured_committed_usd: float = 0.0
    csp_cash_available_usd: float = 0.0
    try:
        from app.core.portfolio.sizing_r260 import (
            compute_available_budget,
            compute_cash_secured_committed,
            compute_available_cash_for_new_csp,
        )
        budget_snap = {"cash": snap.get("cash"), "total_equity": metrics.get("total_equity"), "symbol_notionals": metrics.get("symbol_notionals")}
        available_budget_usd = compute_available_budget(budget_snap, cfg)
        snap_for_csp = {"cash": snap.get("cash"), "total_equity": metrics.get("total_equity"), "total_capital": snap.get("total_capital"), "option_positions": snap.get("option_positions") or []}
        cash_secured_committed_usd = compute_cash_secured_committed(snap_for_csp)
        csp_cash_available_usd = compute_available_cash_for_new_csp(snap_for_csp, cfg)
    except Exception:
        pass
    return {
        "status": status,
        "metrics": {
            "cash_reserve_pct": round(metrics["cash_reserve_pct"], 2),
            "open_options_count": metrics["open_options_count"],
            "open_shares_count": metrics["open_shares_count"],
            "symbols_exposure_count": metrics["symbols_exposure_count"],
            "max_symbol_notional_pct": round(metrics["max_symbol_notional_pct"], 2),
            "available_budget_usd": round(available_budget_usd, 2),
            "cash_secured_committed_usd": round(cash_secured_committed_usd, 2),
            "csp_cash_available_usd": round(csp_cash_available_usd, 2),
        },
        "limits": {
            "MAX_OPEN_OPTIONS_POSITIONS": max_options,
            "MAX_OPEN_SHARES_POSITIONS": max_shares,
            "MAX_SYMBOLS_EXPOSURE": max_symbols,
            "MAX_NOTIONAL_PER_SYMBOL_PCT": max_notional_pct,
            "MIN_CASH_RESERVE_PCT": min_cash_pct,
        },
    }
