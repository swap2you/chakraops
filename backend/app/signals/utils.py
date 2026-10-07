# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Pure helper functions for signal calculations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def calc_dte(as_of: datetime, expiry: date) -> int:
    """Calculate Days To Expiration.

    Args:
        as_of: Reference datetime (typically current time or snapshot time)
        expiry: Option expiration date

    Returns:
        Number of days until expiration (can be negative if expiry is in the past)

    Examples:
        >>> from datetime import datetime, date
        >>> calc_dte(datetime(2026, 1, 22), date(2026, 2, 20))
        29
        >>> calc_dte(datetime(2026, 1, 22), date(2026, 1, 20))
        -2
    """
    as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.date()
    delta = expiry - as_of_date
    return delta.days


def mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Calculate mid price from bid and ask.

    Args:
        bid: Bid price (can be None or 0)
        ask: Ask price (can be None or 0)

    Returns:
        Mid price = (bid + ask) / 2, or None if either is None or both are 0

    Examples:
        >>> mid(2.50, 2.60)
        2.55
        >>> mid(2.50, None)
        None
        >>> mid(None, 2.60)
        None
        >>> mid(0.0, 0.0)
        None
        >>> mid(2.50, 0.0)
        1.25
    """
    if bid is None or ask is None:
        return None
    if bid == 0.0 and ask == 0.0:
        return None
    return (bid + ask) / 2.0


def spread_pct(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Calculate bid-ask spread as a percentage of mid price.

    Args:
        bid: Bid price (can be None or 0)
        ask: Ask price (can be None or 0)

    Returns:
        Spread percentage = (ask - bid) / mid * 100, or None if:
        - Either bid or ask is None
        - Both bid and ask are 0
        - Mid price is 0 (division by zero protection)
        - bid > ask (invalid quote)

    Examples:
        >>> spread_pct(2.50, 2.60)
        3.9215686274509802  # (0.10 / 2.55) * 100
        >>> spread_pct(2.50, None)
        None
        >>> spread_pct(0.0, 0.0)
        None
        >>> spread_pct(2.60, 2.50)  # bid > ask
        None
    """
    if bid is None or ask is None:
        return None

    # Handle zero case
    if bid == 0.0 and ask == 0.0:
        return None

    # Validate bid <= ask
    if bid > ask:
        return None

    # Calculate mid
    mid_price = (bid + ask) / 2.0
    if mid_price == 0.0:
        return None

    # Calculate spread percentage
    spread = ask - bid
    return (spread / mid_price) * 100.0


__all__ = [
    "calc_dte",
    "mid",
    "spread_pct",
]
