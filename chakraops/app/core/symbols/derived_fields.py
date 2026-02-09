# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8E: Derived field promotion.

If a required field is derivable, it is NOT missing.
Derivation is explicit, logged, and surfaced in diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class DerivedValues:
    """Result of deriving missing fields from available data."""
    mid_price: Optional[float] = None  # (bid + ask) / 2 when both exist
    synthetic_bid: Optional[float] = None  # from mid or ask when only one of bid/ask
    synthetic_ask: Optional[float] = None
    open_interest_aggregate: Optional[int] = None  # from strikes aggregation when available
    sources: Dict[str, str] = field(default_factory=dict)  # field -> "ORATS" | "DERIVED" | "CACHED"


def derive_equity_fields(
    price: Optional[float] = None,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    volume: Optional[int] = None,
) -> DerivedValues:
    """
    Pure function: derive mid_price and synthetic bid/ask when possible.

    - mid_price = (bid + ask) / 2 when both exist
    - When only one of bid/ask exists, use it as synthetic for both (proxy for mid)
    - Log derivation when applied
    """
    out = DerivedValues()
    if bid is not None and ask is not None:
        try:
            out.mid_price = (float(bid) + float(ask)) / 2.0
            out.sources["mid_price"] = "DERIVED"
            logger.debug("[DERIVED] mid_price=%.4f from bid=%.4f ask=%.4f", out.mid_price, bid, ask)
        except (TypeError, ValueError):
            pass
    elif bid is not None:
        out.synthetic_bid = float(bid)
        out.synthetic_ask = float(bid)
        out.sources["synthetic_bid_ask"] = "DERIVED"
        logger.debug("[DERIVED] synthetic_bid_ask=%.4f from bid only", bid)
    elif ask is not None:
        out.synthetic_bid = float(ask)
        out.synthetic_ask = float(ask)
        out.sources["synthetic_bid_ask"] = "DERIVED"
        logger.debug("[DERIVED] synthetic_bid_ask=%.4f from ask only", ask)

    return out


def effective_bid(raw_bid: Optional[float], derived: DerivedValues) -> Optional[float]:
    """Return bid: raw if present, else synthetic from derivation."""
    if raw_bid is not None:
        return raw_bid
    if derived.synthetic_bid is not None:
        return derived.synthetic_bid
    return None


def effective_ask(raw_ask: Optional[float], derived: DerivedValues) -> Optional[float]:
    """Return ask: raw if present, else synthetic from derivation."""
    if raw_ask is not None:
        return raw_ask
    if derived.synthetic_ask is not None:
        return derived.synthetic_ask
    return None


def effective_mid(price: Optional[float], bid: Optional[float], ask: Optional[float], derived: DerivedValues) -> Optional[float]:
    """Return mid price: derived mid_price if set, else (bid+ask)/2, else price as fallback."""
    if derived.mid_price is not None:
        return derived.mid_price
    if bid is not None and ask is not None:
        try:
            return (float(bid) + float(ask)) / 2.0
        except (TypeError, ValueError):
            pass
    if derived.synthetic_bid is not None:
        return derived.synthetic_bid
    return price


__all__ = [
    "DerivedValues",
    "derive_equity_fields",
    "effective_bid",
    "effective_ask",
    "effective_mid",
]
