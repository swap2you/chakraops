# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 5.2: Intraday candle provider (4H). ORATS does not expose intraday; stub returns None.

If ORATS adds an intraday endpoint later, implement here with same shape:
  list of {ts, open, high, low, close, volume}, ascending, minimum INTRADAY_MIN_ROWS.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_intraday_candles(
    symbol: str,
    timeframe: str = "4H",
    lookback: int = 200,
) -> Optional[List[Dict[str, Any]]]:
    """
    Return intraday candles for symbol or None if unavailable.
    ORATS does not provide intraday; this stub always returns None.
    Normalized shape: [{ts, open, high, low, close, volume}, ...], ascending, len >= INTRADAY_MIN_ROWS.
    """
    # ORATS has no intraday endpoint; no external data allowed per constraints
    _ = symbol, timeframe, lookback
    return None
