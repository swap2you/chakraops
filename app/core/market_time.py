# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market time awareness for trading operations (Phase 1C).

This module provides market state detection:
- OPEN: Market is currently open
- CLOSED: Market is closed (after hours or before market open)
- PRE-MARKET: Pre-market hours (4:00 AM - 9:30 AM ET)
- WEEKEND: Weekend (Saturday or Sunday)
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal

import pytz

MarketState = Literal["OPEN", "CLOSED", "PRE_MARKET", "WEEKEND"]


def get_market_state(now: Optional[datetime] = None) -> MarketState:
    """Get current market state.
    
    Parameters
    ----------
    now:
        Optional datetime to check (defaults to now in ET timezone).
    
    Returns
    -------
    MarketState
        One of: "OPEN", "CLOSED", "PRE_MARKET", "WEEKEND"
    """
    if pytz is None:
        # Fallback: assume market is open if pytz not available
        return "OPEN"
    
    if now is None:
        now = datetime.now(pytz.timezone("America/New_York"))
    else:
        # Convert to ET if not already
        if now.tzinfo is None:
            now = pytz.timezone("America/New_York").localize(now)
        else:
            now = now.astimezone(pytz.timezone("America/New_York"))
    
    # Check if weekend
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    if weekday >= 5:  # Saturday or Sunday
        return "WEEKEND"
    
    current_time = now.time()
    
    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = time(9, 30)
    market_close = time(16, 0)
    
    # Pre-market: 4:00 AM - 9:30 AM ET
    pre_market_start = time(4, 0)
    
    if market_open <= current_time < market_close:
        return "OPEN"
    elif pre_market_start <= current_time < market_open:
        return "PRE_MARKET"
    else:
        return "CLOSED"


def is_market_open() -> bool:
    """Check if market is currently open.
    
    Returns
    -------
    bool
        True if market is OPEN, False otherwise.
    """
    return get_market_state() == "OPEN"


__all__ = ["get_market_state", "is_market_open", "MarketState"]
