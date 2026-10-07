#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Option selection helpers for the ChakraOps wheel engine.

This module is intentionally small and pure: it contains only stateless helper
functions that operate on in-memory option chain data (e.g. from ORATS).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class _RankedContract:
    """Internal helper structure used for ranking candidate contracts."""

    symbol: str
    expiry_date: date
    strike: float
    delta: float
    bid: float
    ask: float
    oi: int
    spread: float


def _parse_expiry(value: Any) -> Optional[date]:
    """Best-effort parser to convert an expiry field into a ``date``.

    Accepts:
    - ``datetime.date`` instances (returned as-is)
    - ``datetime.datetime`` instances (date component only)
    - ISO date strings (``YYYY-MM-DD``)
    """
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None

    return None


def select_short_put(
    chain: List[Dict[str, Any]],
    dte_min: int,
    dte_max: int,
    delta_min: float,
    delta_max: float,
) -> Optional[Dict[str, Any]]:
    """Select a single short put candidate from an options chain.

    The function is **pure** and has no side effects. It operates only on the
    provided ``chain`` data and returns a dictionary describing the preferred
    contract, or ``None`` if no contract passes the safety filters.

    Selection steps
    ---------------
    1. Filter expirations to those whose days-to-expiry (DTE) is within
       ``[dte_min, dte_max]``.
    2. Filter to puts whose delta is within ``[delta_min, delta_max]``.
       (This function does not infer call/put from other fields; the caller
       should pass an appropriate delta range for puts, e.g. -0.35 to -0.15.)
    3. Rank remaining contracts by:
       - Highest open interest (OI)
       - Then tightest bid/ask spread
    """
    if not chain:
        return None

    today = date.today()
    ranked: List[_RankedContract] = []

    for row in chain:
        if not isinstance(row, dict):
            continue

        expiry_raw = row.get("expiry") or row.get("expirationDate") or row.get("expDate")
        expiry_date = _parse_expiry(expiry_raw)
        if expiry_date is None:
            continue

        dte = (expiry_date - today).days
        if dte < dte_min or dte > dte_max:
            continue

        # Extract core numeric fields safely
        try:
            delta = float(row.get("delta"))
            strike = float(row.get("strike") or row.get("strikePrice"))
            bid = float(row.get("bid") or row.get("bidPrice"))
            ask = float(row.get("ask") or row.get("askPrice"))
            oi_raw = row.get("oi") or row.get("openInterest") or row.get("open_interest") or 0
            oi = int(oi_raw)
        except (TypeError, ValueError):
            # Skip rows with non-numeric fields
            continue

        # Basic sanity checks
        if bid < 0 or ask <= 0 or ask < bid:
            continue

        # Delta filter for puts
        if not (delta_min <= delta <= delta_max):
            continue

        spread = ask - bid

        symbol = (
            row.get("symbol")
            or row.get("underlying")
            or row.get("ticker")
            or ""
        )

        ranked.append(
            _RankedContract(
                symbol=symbol,
                expiry_date=expiry_date,
                strike=strike,
                delta=delta,
                bid=bid,
                ask=ask,
                oi=oi,
                spread=spread,
            )
        )

    if not ranked:
        return None

    # Rank by highest OI, then tightest spread.
    ranked.sort(key=lambda c: (-c.oi, c.spread))
    best = ranked[0]

    return {
        "symbol": best.symbol,
        "expiry_date": best.expiry_date,
        "strike": best.strike,
        "delta": best.delta,
        "bid": best.bid,
        "ask": best.ask,
        "oi": best.oi,
    }


__all__ = ["select_short_put"]

