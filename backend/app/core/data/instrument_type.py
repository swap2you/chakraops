# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Instrument classification for data contract (Phase 8E).

Re-exports from app.core.symbols.instrument_type — single implementation.
"""

from app.core.symbols.instrument_type import (
    InstrumentType,
    KNOWN_ETF_SYMBOLS,
    classify_instrument,
    get_required_fields_for_instrument,
    get_optional_liquidity_fields_for_instrument,
    clear_instrument_cache,
)

__all__ = [
    "InstrumentType",
    "KNOWN_ETF_SYMBOLS",
    "classify_instrument",
    "get_required_fields_for_instrument",
    "get_optional_liquidity_fields_for_instrument",
    "clear_instrument_cache",
]
