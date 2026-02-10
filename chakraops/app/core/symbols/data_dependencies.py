# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6: Data dependency enforcement — required/optional/stale from data_dependencies.md.
Phase 8E: Instrument-type-specific required fields (ETF/INDEX: bid, ask, open_interest optional)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.environment.market_calendar import trading_days_since

logger = logging.getLogger(__name__)

# Global required set (EQUITY): used when instrument type unknown or for backward compatibility
REQUIRED_EVALUATION_FIELDS = ["price", "iv_rank", "bid", "ask", "volume", "quote_date"]
# Phase 8E: ETF/INDEX never require bid, ask, open_interest for DATA_INCOMPLETE
REQUIRED_EVALUATION_FIELDS_EQUITY = ["price", "iv_rank", "bid", "ask", "volume", "quote_date"]
REQUIRED_EVALUATION_FIELDS_ETF_INDEX = ["price", "iv_rank", "volume", "quote_date"]
# Volume: only avg_option_volume_20d (cores) or avg_stock_volume_20d (derived). No avg_volume (does not exist in ORATS).
OPTIONAL_EVALUATION_FIELDS: List[str] = []  # No optional fields that block; volume metrics are informational
STALENESS_TRADING_DAYS = 1


def _parse_date_from_value(val: Any) -> Optional[date]:
    """Parse date from ISO string or YYYY-MM-DD. Returns None if invalid."""
    if val is None:
        return None
    s = str(val).strip()[:10]
    if len(s) < 10:
        return None
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, IndexError):
        return None


def _data_as_of_from_symbol(sym: Dict[str, Any]) -> Optional[date]:
    """Best available data-as-of date from symbol (quote_date preferred, else fetched_at date part)."""
    quote = sym.get("quote_date")
    d = _parse_date_from_value(quote)
    if d is not None:
        return d
    fetched = sym.get("fetched_at")
    return _parse_date_from_value(fetched)


def _required_fields_for_symbol(sym: Dict[str, Any]) -> List[str]:
    """Phase 8E: Required fields depend on instrument type. ETF/INDEX do not require bid, ask, open_interest."""
    try:
        from app.core.symbols.instrument_type import classify_instrument, get_required_fields_for_instrument
        symbol = (sym.get("symbol") or "").strip().upper()
        if not symbol:
            return list(REQUIRED_EVALUATION_FIELDS_EQUITY)
        inst = classify_instrument(symbol)
        return list(get_required_fields_for_instrument(inst))
    except Exception as e:
        logger.debug("[DATA_DEPS] instrument classification failed: %s; using EQUITY rules", e)
        return list(REQUIRED_EVALUATION_FIELDS_EQUITY)


def compute_required_missing(sym: Dict[str, Any]) -> List[str]:
    """Return list of required fields that are missing. Instrument-type-aware (8E): ETF/INDEX do not require bid/ask/OI."""
    required = _required_fields_for_symbol(sym)
    missing: List[str] = []
    for f in required:
        val = sym.get(f)
        if val is None:
            missing.append(f)
        elif f == "iv_rank" and sym.get("iv_rank") is None:
            missing.append(f)
    # Delta for primary candidate: if we have candidate_trades/selected_contract, delta is required
    trade = _primary_candidate(sym)
    if trade and sym.get("verdict") == "ELIGIBLE":
        delta = trade.get("delta") if isinstance(trade, dict) else getattr(trade, "delta", None)
        if delta is None:
            missing.append("delta")
    return missing


def _primary_candidate(sym: Dict[str, Any]) -> Optional[Any]:
    """First candidate trade or selected_contract for primary strategy."""
    candidates = sym.get("candidate_trades") or []
    strategy = sym.get("primary_strategy")
    if not strategy and candidates:
        first = candidates[0]
        strategy = first.get("strategy") if isinstance(first, dict) else getattr(first, "strategy", None)
    for c in candidates:
        c_strat = c.get("strategy") if isinstance(c, dict) else getattr(c, "strategy", None)
        if c_strat == strategy:
            return c
    sc = sym.get("selected_contract")
    if sc and isinstance(sc, dict):
        contract = sc.get("contract") or sc
        if isinstance(contract, dict) and contract.get("delta") is not None:
            return contract
    return None


def compute_optional_missing(sym: Dict[str, Any]) -> List[str]:
    """Return list of optional fields that are missing."""
    missing: List[str] = []
    for f in OPTIONAL_EVALUATION_FIELDS:
        if sym.get(f) is None:
            missing.append(f)
    return missing


def compute_required_stale(
    sym: Dict[str, Any],
    max_trading_days: int = STALENESS_TRADING_DAYS,
) -> List[str]:
    """Return list of required field names that are stale (data older than max_trading_days)."""
    as_of = _data_as_of_from_symbol(sym)
    if as_of is None:
        return list(REQUIRED_EVALUATION_FIELDS)
    days = trading_days_since(as_of)
    if days is None:
        return []
    if days > max_trading_days:
        return list(REQUIRED_EVALUATION_FIELDS)
    return []


def get_data_as_of(sym: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Return provider-level timestamps for API. Keys: data_as_of_orats, data_as_of_price."""
    quote = sym.get("quote_date")
    fetched = sym.get("fetched_at")
    as_of = quote if quote else fetched
    return {
        "data_as_of_orats": str(as_of) if as_of else None,
        "data_as_of_price": str(as_of) if as_of else None,
    }


def compute_dependency_lists(
    sym: Dict[str, Any],
    max_stale_trading_days: int = STALENESS_TRADING_DAYS,
) -> Tuple[List[str], List[str], List[str], Dict[str, Optional[str]]]:
    """
    Compute required_data_missing, optional_data_missing, required_data_stale, data_as_of.

    Returns:
        (required_data_missing, optional_data_missing, required_data_stale, data_as_of_dict)
    """
    required_missing = compute_required_missing(sym)
    optional_missing = compute_optional_missing(sym)
    required_stale = compute_required_stale(sym, max_trading_days=max_stale_trading_days)
    data_as_of = get_data_as_of(sym)
    return required_missing, optional_missing, required_stale, data_as_of


def dependency_status(
    required_data_missing: List[str],
    required_data_stale: List[str],
    optional_data_missing: List[str],
) -> str:
    """
    Derive data_sufficiency status from dependency lists (Phase 6).

    PASS: required_data_missing empty AND required_data_stale empty
    FAIL: required_data_missing non-empty
    WARN: optional_data_missing non-empty OR required_data_stale non-empty (and no required missing)
    """
    if required_data_missing:
        return "FAIL"
    if required_data_stale:
        return "WARN"
    if optional_data_missing:
        return "WARN"
    return "PASS"


def all_missing_fields(
    required_data_missing: List[str],
    optional_data_missing: List[str],
) -> List[str]:
    """Combined list of missing fields (required first, then optional) for API/UI."""
    out = list(required_data_missing)
    for f in optional_data_missing:
        if f not in out:
            out.append(f)
    return out
