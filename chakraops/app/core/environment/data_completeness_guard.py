# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Data completeness execution guard (Phase 4.5.4).

Fail closed when required data for trade construction is missing.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

from app.signals.models import ExclusionReason
from app.signals.selection import SelectedSignal

# Optional: OptionContext lives in app.models
try:
    from app.models.option_context import OptionContext
except ImportError:
    OptionContext = Any  # type: ignore[misc, assignment]


def check_data_completeness(
    signal: SelectedSignal,
    option_context: Optional["OptionContext"],
) -> Optional[ExclusionReason]:
    """Return an ExclusionReason if required data for trade construction is missing; else None.

    Required for trade construction:
    - expected_move_1sd (from option_context)
    - underlying price (positive, finite)
    - option chain liquidity: at least one of bid/mid for pricing; open_interest as liquidity flag

    Parameters
    ----------
    signal : SelectedSignal
        Selected signal (signal.scored.candidate has underlying_price, bid, mid, open_interest).
    option_context : Optional[OptionContext]
        Volatility/context; must provide expected_move_1sd.

    Returns
    -------
    Optional[ExclusionReason]
        DATA_INCOMPLETE with message and data listing missing fields if incomplete; None if complete.
    """
    missing: List[str] = []
    candidate = signal.scored.candidate
    symbol = getattr(candidate, "symbol", "")

    # expected_move_1sd (required for risk-first CSP/credit spread)
    em = None
    if option_context is not None:
        em = getattr(option_context, "expected_move_1sd", None)
    if em is None or (isinstance(em, (int, float)) and (math.isnan(em) or em <= 0)):
        missing.append("expected_move_1sd")

    # underlying price (required, positive, finite)
    up = getattr(candidate, "underlying_price", None)
    if up is None or not isinstance(up, (int, float)):
        missing.append("underlying_price")
    elif math.isnan(up) or math.isinf(up) or up <= 0:
        missing.append("underlying_price")

    # option chain liquidity: at least one of bid or mid for pricing
    bid = getattr(candidate, "bid", None)
    mid = getattr(candidate, "mid", None)
    has_price = (bid is not None and not (isinstance(bid, float) and math.isnan(bid))) or (
        mid is not None and not (isinstance(mid, float) and math.isnan(mid))
    )
    if not has_price:
        missing.append("bid_or_mid")

    # open_interest as liquidity flag (required for trade construction confidence)
    oi = getattr(candidate, "open_interest", None)
    if oi is None:
        missing.append("open_interest")

    if not missing:
        return None

    return ExclusionReason(
        code="DATA_INCOMPLETE",
        message=f"Required data missing for trade construction ({symbol}): {', '.join(missing)}",
        data={"symbol": symbol, "missing": missing},
    )
