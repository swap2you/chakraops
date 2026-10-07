# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8E: Instrument classification for conditional data requirements.

ETF/INDEX instruments (e.g. SPY, QQQ) may have missing bid/ask/open_interest from ORATS;
they must never be marked DATA_INCOMPLETE solely for those fields.
Classification is deterministic and cached.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class InstrumentType(str, Enum):
    """Instrument type for data sufficiency rules."""
    EQUITY = "EQUITY"
    ETF = "ETF"
    INDEX = "INDEX"


# Known ETF/index-like symbols (ORATS often omits bid/ask/OI for these)
KNOWN_ETF_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "DIA"})

# Cache: symbol -> InstrumentType (deterministic, process-life)
_classification_cache: dict[str, InstrumentType] = {}


def classify_instrument(symbol: str, metadata: Optional[dict] = None) -> InstrumentType:
    """
    Classify symbol as EQUITY, ETF, or INDEX. Deterministic; result is cached.

    Rules:
    - SPY, QQQ, IWM, DIA -> ETF
    - Symbol with no company fundamentals (metadata) -> INDEX
    - Else -> EQUITY

    Args:
        symbol: Ticker symbol (e.g. AAPL, SPY)
        metadata: Optional pre-fetched company metadata (if None, we try get_company_metadata)

    Returns:
        InstrumentType
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return InstrumentType.EQUITY

    cached = _classification_cache.get(sym)
    if cached is not None:
        return cached

    if sym in KNOWN_ETF_SYMBOLS:
        result = InstrumentType.ETF
        logger.debug("[INSTRUMENT] %s -> ETF (known list)", sym)
    else:
        if metadata is None:
            try:
                from app.core.market.company_data import get_company_metadata
                metadata = get_company_metadata(sym)
            except Exception as e:
                logger.debug("[INSTRUMENT] %s metadata lookup failed: %s; treating as INDEX", sym, e)
                metadata = None
        if metadata is None or (not metadata.get("sector") and not metadata.get("industry")):
            result = InstrumentType.INDEX
            logger.debug("[INSTRUMENT] %s -> INDEX (no fundamentals)", sym)
        else:
            result = InstrumentType.EQUITY
            logger.debug("[INSTRUMENT] %s -> EQUITY", sym)

    _classification_cache[sym] = result
    return result


def get_required_fields_for_instrument(instrument_type: InstrumentType) -> tuple[str, ...]:
    """
    Required fields for data sufficiency by instrument type.

    EQUITY: price, volume, iv_rank, bid, ask, quote_date, open_interest (stock-level OI from chain)
    ETF/INDEX: price, volume, iv_rank, quote_date only (bid, ask, open_interest OPTIONAL)
    """
    if instrument_type in (InstrumentType.ETF, InstrumentType.INDEX):
        return ("price", "volume", "iv_rank", "quote_date")
    return ("price", "iv_rank", "bid", "ask", "volume", "quote_date")


def get_optional_liquidity_fields_for_instrument(instrument_type: InstrumentType) -> tuple[str, ...]:
    """Fields that are optional for ETF/INDEX (required for EQUITY)."""
    if instrument_type in (InstrumentType.ETF, InstrumentType.INDEX):
        return ("bid", "ask", "open_interest")
    return ()


def clear_instrument_cache() -> None:
    """Clear classification cache (e.g. for tests)."""
    global _classification_cache
    _classification_cache = {}


__all__ = [
    "InstrumentType",
    "KNOWN_ETF_SYMBOLS",
    "classify_instrument",
    "get_required_fields_for_instrument",
    "get_optional_liquidity_fields_for_instrument",
    "clear_instrument_cache",
]
