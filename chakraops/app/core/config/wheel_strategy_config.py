# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Wheel strategy configuration (Phase 3.2.1).

Single source of truth for Wheel/CSP parameters. No hardcoded numbers elsewhere;
import from this module (e.g. WHEEL_CONFIG, DTE_MIN, get_wheel_config).
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

# Key names for WHEEL_CONFIG (use these when indexing the dict elsewhere)
DTE_MIN = "DTE_MIN"
DTE_MAX = "DTE_MAX"
TARGET_DELTA_RANGE = "TARGET_DELTA_RANGE"
MIN_UNDERLYING_VOLUME = "MIN_UNDERLYING_VOLUME"
MAX_UNDERLYING_SPREAD_PCT = "MAX_UNDERLYING_SPREAD_PCT"
MIN_OPTION_OI = "MIN_OPTION_OI"
MAX_OPTION_SPREAD_PCT = "MAX_OPTION_SPREAD_PCT"
EARNINGS_WINDOW_DAYS = "EARNINGS_WINDOW_DAYS"
IVR_BANDS = "IVR_BANDS"
PROFIT_EXIT_PCT = "PROFIT_EXIT_PCT"
MAX_POSITION_RISK_PCT = "MAX_POSITION_RISK_PCT"

# IVR band key names (for IVR_BANDS sub-dict)
IVR_LOW = "LOW"
IVR_MID = "MID"
IVR_HIGH = "HIGH"

WHEEL_CONFIG: Dict[str, Any] = {
    # Minimum days to expiration for opening a short put (CSP). Filters out
    # expirations closer than this; typical Wheel uses 30–45 DTE.
    DTE_MIN: 30,

    # Maximum days to expiration for opening a short put. Avoids selling
    # too far out; keeps premium and assignment risk in a target range.
    DTE_MAX: 45,

    # (min_delta, max_delta) for put selection, as absolute delta (e.g. 0.15–0.35).
    # Short puts in this range balance premium vs. probability of assignment.
    TARGET_DELTA_RANGE: (0.15, 0.35),

    # Minimum average daily share volume (20d or similar) for the underlying.
    # Ensures liquid underlyings; below this the symbol is excluded from Wheel.
    MIN_UNDERLYING_VOLUME: 1_500_000,

    # Maximum allowed underlying bid-ask spread as fraction of mid (e.g. 0.01 = 1%).
    # Above this the stock is considered too wide for reliable pricing.
    MAX_UNDERLYING_SPREAD_PCT: 0.01,

    # Minimum open interest per option contract. Contracts below this are
    # excluded for liquidity (hard to exit or adjust).
    MIN_OPTION_OI: 500,

    # Maximum allowed option bid-ask spread as fraction of mid (e.g. 0.10 = 10%).
    # Above this the option is considered illiquid for opening/closing.
    MAX_OPTION_SPREAD_PCT: 0.10,

    # Number of days before/after earnings to avoid opening or holding through
    # earnings (block/warn window). No new CSP within this window of an event.
    EARNINGS_WINDOW_DAYS: 7,

    # IV Rank bands (percentiles 0–100). Used for regime-aware behavior:
    # LOW = depressed IV (e.g. wait for better premium), MID = normal,
    # HIGH = elevated IV (favor premium selling). Values are (low_pct, high_pct)
    # for each band; LOW is 0–25, MID 25–75, HIGH 75–100.
    IVR_BANDS: {
        IVR_LOW: (0, 25),
        IVR_MID: (25, 75),
        IVR_HIGH: (75, 100),
    },

    # Close (buy back) a short option when unrealized profit reaches this
    # fraction of credit received (e.g. 0.50 = 50% profit target).
    PROFIT_EXIT_PCT: 0.50,

    # Maximum fraction of portfolio risk (or capital) per position. Caps
    # position size so a single assignment does not exceed this share of portfolio.
    MAX_POSITION_RISK_PCT: 0.05,
}


def get_wheel_config() -> Dict[str, Any]:
    """Return the Wheel strategy config dict. Prefer this for overrides/env later."""
    return dict(WHEEL_CONFIG)


def get_dte_range() -> Tuple[int, int]:
    """Return (DTE_MIN, DTE_MAX) from config."""
    return (WHEEL_CONFIG[DTE_MIN], WHEEL_CONFIG[DTE_MAX])


def get_target_delta_range() -> Tuple[float, float]:
    """Return (min_delta, max_delta) for put selection."""
    return tuple(WHEEL_CONFIG[TARGET_DELTA_RANGE])  # type: ignore[return-value]


def get_ivr_bands() -> Dict[str, Tuple[float, float]]:
    """Return IVR_BANDS dict (LOW, MID, HIGH) -> (low_pct, high_pct)."""
    return dict(WHEEL_CONFIG[IVR_BANDS])  # type: ignore[arg-type]


__all__ = [
    "WHEEL_CONFIG",
    "DTE_MIN",
    "DTE_MAX",
    "TARGET_DELTA_RANGE",
    "MIN_UNDERLYING_VOLUME",
    "MAX_UNDERLYING_SPREAD_PCT",
    "MIN_OPTION_OI",
    "MAX_OPTION_SPREAD_PCT",
    "EARNINGS_WINDOW_DAYS",
    "IVR_BANDS",
    "IVR_LOW",
    "IVR_MID",
    "IVR_HIGH",
    "PROFIT_EXIT_PCT",
    "MAX_POSITION_RISK_PCT",
    "get_wheel_config",
    "get_dte_range",
    "get_target_delta_range",
    "get_ivr_bands",
]
