# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.0: Portfolio-aware position sizing (Wheel: CSP/CC + shares).

Deterministic: same snapshot + guardrails -> same sizing. Safe codes only (no FAIL/WARN).
Manual execution only.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# Safe constraint codes (no FAIL/WARN)
CONSTRAINT_CASH_RESERVE = "CASH_RESERVE"
CONSTRAINT_SYMBOL_CAP = "SYMBOL_CAP"
CONSTRAINT_MAX_OPTIONS_POSITIONS = "MAX_OPTIONS_POSITIONS"
CONSTRAINT_MAX_SHARES_POSITIONS = "MAX_SHARES_POSITIONS"
CONSTRAINT_MAX_SYMBOLS = "MAX_SYMBOLS"
# R26.1: Cash reserved for existing CSP obligations
CONSTRAINT_CASH_SECURED = "CASH_SECURED"

SIZING_RECOMMENDED_BY = "r260"


def compute_available_budget(
    snapshot: Dict[str, Any],
    guardrails_config: Dict[str, Any],
) -> float:
    """
    Cash budget for new entries after MIN_CASH_RESERVE_PCT.
    budget = max(0, cash - total_equity * min_reserve_pct/100).
    """
    cash = float(snapshot.get("cash") or 0)
    total_equity = snapshot.get("total_equity")
    if total_equity is not None:
        try:
            total_equity = float(total_equity)
        except (TypeError, ValueError):
            total_equity = None
    if total_equity is None or total_equity <= 0:
        total_capital = snapshot.get("total_capital")
        if total_capital is not None:
            try:
                total_equity = float(total_capital)
            except (TypeError, ValueError):
                total_equity = cash
        else:
            total_equity = cash
            for _sym, n in (snapshot.get("symbol_notionals") or {}).items():
                total_equity += float(n or 0)
    if total_equity <= 0:
        return 0.0
    min_reserve_pct = float(guardrails_config.get("MIN_CASH_RESERVE_PCT", 25.0))
    reserve = total_equity * (min_reserve_pct / 100.0)
    return max(0.0, cash - reserve)


def compute_cash_secured_committed(snapshot: Dict[str, Any]) -> float:
    """R26.1: Sum of (strike * 100 * contracts) for open CSP positions. Deterministic."""
    total = 0.0
    for op in (snapshot.get("option_positions") or []):
        if (op.get("strategy") or "").strip().upper() != "CSP":
            continue
        contracts = int(op.get("contracts") or 0)
        strike = op.get("strike")
        if contracts <= 0 or strike is None:
            continue
        try:
            total += 100.0 * contracts * float(strike)
        except (TypeError, ValueError):
            continue
    return total


def compute_available_cash_for_new_csp(
    snapshot: Dict[str, Any],
    guardrails_config: Dict[str, Any],
) -> float:
    """
    R26.1: Cash available for new CSP after existing CSP obligations and reserve floor.
    available = cash - cash_secured_committed - reserve_floor.
    """
    cash = float(snapshot.get("cash") or 0)
    committed = compute_cash_secured_committed(snapshot)
    total_equity = snapshot.get("total_equity") or snapshot.get("total_capital")
    if total_equity is not None:
        try:
            total_equity = float(total_equity)
        except (TypeError, ValueError):
            total_equity = cash
    else:
        total_equity = cash
    if total_equity <= 0:
        return 0.0
    min_reserve_pct = float(guardrails_config.get("MIN_CASH_RESERVE_PCT", 25.0))
    reserve_floor = total_equity * (min_reserve_pct / 100.0)
    return max(0.0, cash - committed - reserve_floor)


def max_symbol_budget(
    snapshot: Dict[str, Any],
    guardrails_config: Dict[str, Any],
    symbol: str,
) -> float:
    """
    Max additional notional allowed for symbol under MAX_NOTIONAL_PER_SYMBOL_PCT.
    Returns max(0, allowed_notional - current_symbol_notional).
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return 0.0
    total_equity = float(snapshot.get("total_equity") or 1.0)
    if total_equity <= 0:
        return 0.0
    max_pct = float(guardrails_config.get("MAX_NOTIONAL_PER_SYMBOL_PCT", 15.0))
    max_allowed = total_equity * (max_pct / 100.0)
    symbol_notionals = snapshot.get("symbol_notionals") or {}
    current = float(symbol_notionals.get(symbol) or 0)
    return max(0.0, max_allowed - current)


def size_shares_entry(
    price: float,
    max_additional_notional_usd: float,
) -> int:
    """Shares qty that fits in max_additional_notional_usd. price must be > 0."""
    if not price or price <= 0:
        return 0
    if max_additional_notional_usd <= 0:
        return 0
    return max(0, int(math.floor(max_additional_notional_usd / price)))


def size_csp_entry(
    underlying_price: Optional[float],
    strike: float,
    max_additional_notional_usd: float,
) -> int:
    """CSP contracts: notional proxy = strike * 100 * contracts."""
    if strike is None or strike <= 0:
        return 0
    if max_additional_notional_usd <= 0:
        return 0
    notional_per_contract = strike * 100.0
    return max(0, int(math.floor(max_additional_notional_usd / notional_per_contract)))


def size_cc_entry(
    current_shares_qty: int,
    contract_multiplier: int = 100,
    max_contracts_cap: Optional[int] = None,
) -> int:
    """CC contracts = floor(shares / multiplier), capped by max_contracts_cap (e.g. remaining options slots)."""
    if current_shares_qty <= 0 or contract_multiplier <= 0:
        return 0
    contracts = current_shares_qty // contract_multiplier
    if max_contracts_cap is not None and max_contracts_cap >= 0:
        contracts = min(contracts, max_contracts_cap)
    return max(0, contracts)


def apply_sizing(
    candidate: Dict[str, Any],
    snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    guardrails_config: Optional[Dict[str, Any]] = None,
    symbol_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply portfolio-aware sizing. Returns dict with:
    - blocked: bool (True if size 0 due to caps)
    - recommended_qty / recommended_contracts / recommended_notional_usd
    - sizing_constraints_hit, sizing_recommended_by
    - R26.1 CSP advisory: cash_secured_available_usd, csp_risk_proxy_move_pct,
      csp_risk_proxy_loss_per_contract_usd, csp_risk_proxy_cap_contracts, csp_risk_proxy_enforced
    """
    from app.core.settings import get_guardrails_config
    from app.core.portfolio.risk_proxy_r261 import (
        estimate_downside_move_pct,
        estimate_csp_max_loss_proxy,
        cap_contracts_by_risk_budget,
    )
    cfg = guardrails_config or get_guardrails_config()
    symbol = (candidate.get("symbol") or "").strip().upper()
    strategy = (candidate.get("strategy") or candidate.get("side") or "").strip().upper()
    constraints_hit: List[str] = []

    max_options = int(cfg.get("MAX_OPEN_OPTIONS_POSITIONS", 6))
    max_shares = int(cfg.get("MAX_OPEN_SHARES_POSITIONS", 10))
    max_symbols = int(cfg.get("MAX_SYMBOLS_EXPOSURE", 12))
    open_options = int(metrics.get("open_options_count") or 0)
    open_shares = int(metrics.get("open_shares_count") or 0)
    symbols_count = int(metrics.get("symbols_exposure_count") or 0)
    symbol_notionals = metrics.get("symbol_notionals") or {}
    total_equity = float(metrics.get("total_equity") or 1.0)
    new_symbol = symbol and symbol not in symbol_notionals

    # Snapshot for budget: need total_equity and symbol_notionals; use metrics as snapshot stand-in
    budget_snapshot = {
        "cash": snapshot.get("cash"),
        "total_capital": snapshot.get("total_capital") or total_equity,
        "total_equity": total_equity,
        "symbol_notionals": symbol_notionals,
    }
    available_budget = compute_available_budget(budget_snapshot, cfg)
    symbol_budget = max_symbol_budget(
        {"total_equity": total_equity, "symbol_notionals": symbol_notionals},
        cfg,
        symbol,
    )

    is_options = strategy in ("CSP", "CC", "OPTIONS")
    is_shares = strategy == "SHARES"

    # Position/symbol caps -> size 0
    if is_options and open_options >= max_options:
        constraints_hit.append(CONSTRAINT_MAX_OPTIONS_POSITIONS)
    if is_shares and open_shares >= max_shares:
        constraints_hit.append(CONSTRAINT_MAX_SHARES_POSITIONS)
    if new_symbol and (symbols_count + 1) > max_symbols:
        constraints_hit.append(CONSTRAINT_MAX_SYMBOLS)

    if available_budget <= 0:
        constraints_hit.append(CONSTRAINT_CASH_RESERVE)
    if symbol_budget <= 0 and symbol:
        constraints_hit.append(CONSTRAINT_SYMBOL_CAP)

    # R26.1: CSP cash-secured availability (hard cap)
    strategy = (candidate.get("strategy") or candidate.get("side") or "").strip().upper()
    is_csp = strategy == "CSP"
    snapshot_for_csp = {
        "cash": snapshot.get("cash"),
        "total_equity": snapshot.get("total_equity") or total_equity,
        "total_capital": snapshot.get("total_capital") or total_equity,
        "option_positions": snapshot.get("option_positions") or [],
    }
    available_cash_for_new_csp = compute_available_cash_for_new_csp(snapshot_for_csp, cfg) if is_csp else float("inf")
    if is_csp and available_cash_for_new_csp <= 0:
        constraints_hit.append(CONSTRAINT_CASH_SECURED)

    # If any hard cap hit that forces 0, return blocked
    if CONSTRAINT_MAX_OPTIONS_POSITIONS in constraints_hit or CONSTRAINT_MAX_SHARES_POSITIONS in constraints_hit or CONSTRAINT_MAX_SYMBOLS in constraints_hit:
        return {
            "blocked": True,
            "recommended_qty": None,
            "recommended_contracts": None,
            "recommended_notional_usd": None,
            "sizing_constraints_hit": sorted(constraints_hit),
            "sizing_recommended_by": SIZING_RECOMMENDED_BY,
        }

    effective_budget = min(available_budget, symbol_budget) if symbol else available_budget
    if is_csp:
        effective_budget = min(available_cash_for_new_csp, symbol_budget) if symbol else available_cash_for_new_csp
    if effective_budget <= 0:
        return {
            "blocked": True,
            "recommended_qty": None,
            "recommended_contracts": None,
            "recommended_notional_usd": None,
            "sizing_constraints_hit": sorted(constraints_hit),
            "sizing_recommended_by": SIZING_RECOMMENDED_BY,
        }

    # Size by strategy
    recommended_qty: Optional[int] = None
    recommended_contracts: Optional[int] = None
    recommended_notional_usd: Optional[float] = None
    csp_advisory: Optional[Dict[str, Any]] = None

    if is_shares:
        price = candidate.get("price") or candidate.get("underlying_price") or 0.0
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = 0.0
        qty = size_shares_entry(price, effective_budget)
        recommended_qty = qty
        recommended_notional_usd = (qty * price) if qty and price else None
    elif strategy == "CSP":
        strike = candidate.get("strike")
        underlying = candidate.get("underlying_price") or candidate.get("price")
        try:
            strike = float(strike) if strike is not None else None
        except (TypeError, ValueError):
            strike = None
        try:
            underlying = float(underlying) if underlying is not None else None
        except (TypeError, ValueError):
            underlying = None
        contracts = size_csp_entry(underlying, strike or 0.0, effective_budget)
        recommended_contracts = contracts
        recommended_notional_usd = (contracts * (strike or 0) * 100) if contracts and strike else None
        # R26.1: Risk proxy (advisory or enforced)
        ctx = symbol_context or candidate.get("symbol_context") or {}
        ctx.setdefault("earnings_days_for_move", int(cfg.get("EARNINGS_DAYS_FOR_MOVE", 14)))
        move_pct = estimate_downside_move_pct(ctx)
        options_risk_pct = float(cfg.get("OPTIONS_MAX_RISK_PER_TRADE_PCT", 2.0))
        risk_budget_usd = total_equity * (options_risk_pct / 100.0)
        risk_proxy_cap = cap_contracts_by_risk_budget(risk_budget_usd, strike or 0.0, move_pct)
        risk_proxy_enforced = bool(cfg.get("CSP_RISK_PROXY_ENFORCE", False))
        if risk_proxy_enforced and (recommended_contracts or 0) > risk_proxy_cap:
            recommended_contracts = risk_proxy_cap
            recommended_notional_usd = (risk_proxy_cap * (strike or 0) * 100) if strike else None
        csp_advisory = {
            "cash_secured_available_usd": round(available_cash_for_new_csp, 2),
            "csp_risk_proxy_move_pct": round(move_pct, 2),
            "csp_risk_proxy_loss_per_contract_usd": round(
                estimate_csp_max_loss_proxy(strike or 0.0, 1, move_pct), 2
            ),
            "csp_risk_proxy_cap_contracts": risk_proxy_cap,
            "csp_risk_proxy_enforced": risk_proxy_enforced,
        }
    elif strategy == "CC":
        shares_qty = int(candidate.get("current_shares_qty") or candidate.get("shares") or 0)
        max_contracts_cap = max(0, max_options - open_options) if is_options else None
        contracts = size_cc_entry(shares_qty, 100, max_contracts_cap)
        recommended_contracts = contracts
        # Notional proxy for CC: 100 * contracts * underlying (or 0)
        underlying = candidate.get("underlying_price") or candidate.get("price") or 0.0
        try:
            underlying = float(underlying)
        except (TypeError, ValueError):
            underlying = 0.0
        recommended_notional_usd = (contracts * 100 * underlying) if contracts else None
    else:
        # Generic OPTIONS: treat as CSP if strike present
        strike = candidate.get("strike")
        try:
            strike = float(strike) if strike is not None else None
        except (TypeError, ValueError):
            strike = None
        if strike and strike > 0:
            underlying = candidate.get("underlying_price") or candidate.get("price")
            contracts = size_csp_entry(underlying, strike, effective_budget)
            recommended_contracts = contracts
            recommended_notional_usd = (contracts * strike * 100) if contracts else None
        else:
            recommended_contracts = 0
            recommended_notional_usd = None

    blocked = (recommended_qty or 0) == 0 and (recommended_contracts or 0) == 0
    out = {
        "blocked": blocked,
        "recommended_qty": recommended_qty,
        "recommended_contracts": recommended_contracts,
        "recommended_notional_usd": recommended_notional_usd,
        "sizing_constraints_hit": sorted(constraints_hit),
        "sizing_recommended_by": SIZING_RECOMMENDED_BY,
    }
    if csp_advisory:
        out.update(csp_advisory)
    return out


def get_available_budget_and_symbol_cap(
    snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    guardrails_config: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """For UI: available_budget_usd and max_add_per_symbol_usd (when symbol provided)."""
    from app.core.settings import get_guardrails_config
    cfg = guardrails_config or get_guardrails_config()
    budget_snap = {
        "cash": snapshot.get("cash"),
        "total_capital": snapshot.get("total_capital") or metrics.get("total_equity"),
        "symbol_notionals": metrics.get("symbol_notionals"),
    }
    available_budget_usd = compute_available_budget(budget_snap, cfg)
    max_add_per_symbol_usd: Optional[float] = None
    if symbol:
        max_add_per_symbol_usd = max_symbol_budget(
            {"total_equity": metrics.get("total_equity"), "symbol_notionals": metrics.get("symbol_notionals") or {}},
            cfg,
            symbol,
        )
    return {
        "available_budget_usd": round(available_budget_usd, 2),
        "max_add_per_symbol_usd": round(max_add_per_symbol_usd, 2) if max_add_per_symbol_usd is not None else None,
    }
