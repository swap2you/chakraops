# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 premium fill model — mid ± slippage (SIMULATION assumptions).

Assumptions (documented; intentionally simple for offline research):
1. Quoted ``bid`` / ``ask`` are the only prices; no queue position or partial fills.
2. Mid = (bid + ask) / 2 when both present; else fall back to ``mid`` or ``last``.
3. Selling premium (CSP/CC credit): fill = mid - slippage_abs - mid * slippage_bps/1e4
   (adverse vs mid — we receive less than mid).
4. Buying to close: fill = mid + slippage_abs + mid * slippage_bps/1e4
   (adverse — we pay more than mid).
5. Half-spread option: when ``use_half_spread=True``, slippage_abs defaults to
   half the bid/ask spread if not overridden.
6. No dividends, early assignment, or borrow fees in this model.
7. Fills are deterministic given the same quotes and assumptions — no RNG.
8. Output is always labeled for SIMULATION; never used for live order routing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class FillAssumptions:
    """Fill model knobs. All values are research defaults, not production retunes."""

    slippage_abs: float = 0.0
    slippage_bps: float = 0.0
    use_half_spread: bool = False
    min_premium: float = 0.01

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _mid_from_quote(quote: Mapping[str, Any]) -> Optional[float]:
    bid = quote.get("bid")
    ask = quote.get("ask")
    try:
        if bid is not None and ask is not None:
            b, a = float(bid), float(ask)
            if a >= b >= 0:
                return (a + b) / 2.0
    except (TypeError, ValueError):
        pass
    for key in ("mid", "last", "mark", "price"):
        if quote.get(key) is not None:
            try:
                v = float(quote[key])
                if v > 0:
                    return v
            except (TypeError, ValueError):
                continue
    return None


def _half_spread(quote: Mapping[str, Any]) -> float:
    try:
        bid = float(quote.get("bid"))
        ask = float(quote.get("ask"))
        if ask >= bid >= 0:
            return (ask - bid) / 2.0
    except (TypeError, ValueError):
        pass
    return 0.0


def premium_fill(
    quote: Mapping[str, Any],
    *,
    side: str = "sell",
    assumptions: Optional[FillAssumptions] = None,
) -> Dict[str, Any]:
    """Compute a simulated premium fill from a bid/ask quote.

    Parameters
    ----------
    quote:
        Mapping with bid/ask (preferred) or mid/last.
    side:
        ``sell`` (credit entry) or ``buy`` (debit / BTC).
    assumptions:
        Slippage model; defaults to zero absolute + zero bps.

    Returns
    -------
    dict with fill_price, mid, slippage_applied, side, simulation=True.
    """
    assum = assumptions or FillAssumptions()
    mid = _mid_from_quote(quote)
    if mid is None or mid <= 0:
        return {
            "fill_price": None,
            "mid": None,
            "slippage_applied": None,
            "side": side,
            "simulation": True,
            "error": "no_valid_mid",
        }

    slip = float(assum.slippage_abs)
    if assum.use_half_spread and slip == 0.0:
        slip = _half_spread(quote)
    slip += mid * (float(assum.slippage_bps) / 10_000.0)

    side_n = (side or "sell").strip().lower()
    if side_n in ("sell", "short", "credit"):
        fill = mid - slip
    else:
        fill = mid + slip

    fill = max(float(assum.min_premium), round(fill, 4))
    return {
        "fill_price": fill,
        "mid": round(mid, 4),
        "slippage_applied": round(slip, 6),
        "side": "sell" if side_n in ("sell", "short", "credit") else "buy",
        "simulation": True,
        "assumptions": assum.to_dict(),
    }
