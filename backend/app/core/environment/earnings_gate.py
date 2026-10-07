# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Earnings and corporate event execution gate (Phase 4.5.1).

Blocks new trade proposals when the symbol is within a configured window
of earnings or has an earnings-related event flag.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.option_context import OptionContext
from app.signals.models import ExclusionReason


def check_earnings_gate(
    option_context: Optional[OptionContext],
    config: Dict[str, Any],
) -> Optional[ExclusionReason]:
    """Return an ExclusionReason if the option context fails the earnings gate; else None.

    Rules:
    - If option_context.days_to_earnings is not None and
      days_to_earnings <= config["earnings_block_window_days"] → block with EARNINGS_WINDOW.
    - If option_context.event_flags contains "earnings" → same exclusion.

    Parameters
    ----------
    option_context : Optional[OptionContext]
        Volatility/event context for the symbol. If None, the gate passes (best-effort).
    config : dict
        Must contain "earnings_block_window_days" (int). Block when days_to_earnings <= this.

    Returns
    -------
    Optional[ExclusionReason]
        EARNINGS_WINDOW with message if blocked; None if pass.
    """
    if option_context is None:
        return None

    window_days = config.get("earnings_block_window_days", 7)
    try:
        window_days = int(window_days)
    except (TypeError, ValueError):
        window_days = 7

    symbol = getattr(option_context, "symbol", "")

    # Rule 1: days_to_earnings within block window
    days_to_earnings = getattr(option_context, "days_to_earnings", None)
    if days_to_earnings is not None and window_days >= 0:
        try:
            dte = int(days_to_earnings)
            if dte <= window_days:
                return ExclusionReason(
                    code="EARNINGS_WINDOW",
                    message=(
                        f"Earnings in {dte} days within block window {window_days} ({symbol})"
                    ),
                    data={
                        "symbol": symbol,
                        "days_to_earnings": dte,
                        "earnings_block_window_days": window_days,
                    },
                )
        except (TypeError, ValueError):
            pass

    # Rule 2: event_flags contains "earnings"
    event_flags = getattr(option_context, "event_flags", None) or []
    if event_flags and "earnings" in [str(f).lower() for f in event_flags]:
        return ExclusionReason(
            code="EARNINGS_WINDOW",
            message=f"Earnings event flag set ({symbol})",
            data={
                "symbol": symbol,
                "event_flags": list(event_flags),
                "earnings_block_window_days": window_days,
            },
        )

    return None
