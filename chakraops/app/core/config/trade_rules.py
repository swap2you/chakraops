# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Trade rule configuration constants.

This module contains configuration values for CSP (Cash-Secured Put) trading rules.
These are pure constants with no business logic.

All values are subject to change based on strategy refinement.
"""

from __future__ import annotations

# Days to Expiration (DTE) constraints for CSP positions
CSP_MIN_DTE: int = 30
"""Minimum days to expiration for CSP contracts.

Contracts with fewer days to expiration are excluded from consideration
to avoid excessive gamma risk and time decay pressure.
"""

CSP_MAX_DTE: int = 45
"""Maximum days to expiration for CSP contracts.

Contracts with more days to expiration are excluded to maintain
reasonable time horizons and avoid tying up capital for extended periods.
"""

# Delta range for CSP contract selection
CSP_TARGET_DELTA_LOW: float = 0.25
"""Lower bound of target delta range for CSP contracts.

This represents the minimum acceptable delta (probability of finishing
in-the-money). Lower deltas indicate lower probability of assignment
but also lower premium collection.
"""

CSP_TARGET_DELTA_HIGH: float = 0.35
"""Upper bound of target delta range for CSP contracts.

This represents the maximum acceptable delta. Higher deltas indicate
higher probability of assignment but also higher premium collection.
The range [CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH] defines
the acceptable delta window for contract selection.
"""

# Capital allocation constraints
MAX_CAPITAL_PER_SYMBOL_PCT: float = 0.15
"""Maximum percentage of total capital to allocate per symbol.

This enforces position sizing discipline by limiting exposure to any
single underlying. Expressed as a decimal (0.15 = 15%).
"""

# CSP Scoring price constraints (Phase 2B Step 2)
MIN_PRICE: float = 20.0
"""Minimum stock price for CSP candidate eligibility.

Stocks priced below this threshold are excluded from CSP consideration.
"""

MAX_PRICE: float = 500.0
"""Maximum stock price for CSP candidate eligibility.

Stocks priced above this threshold are excluded from CSP consideration.
"""

TARGET_LOW: float = 50.0
"""Lower bound of optimal price range for CSP candidates.

Stocks in the range [TARGET_LOW, TARGET_HIGH] receive maximum price suitability score.
"""

TARGET_HIGH: float = 250.0
"""Upper bound of optimal price range for CSP candidates.

Stocks in the range [TARGET_LOW, TARGET_HIGH] receive maximum price suitability score.
"""

# R23.2: Near-miss and delta override (advanced)
DELTA_NEAR_MISS_EPS: float = 0.02
"""If rejected due to delta and miss <= this, add DELTA_NEAR_MISS to primary_reason_codes (code-only)."""

DELTA_OVERRIDE_MAX_WIDEN: float = 0.05
"""Hard cap: per-symbol delta override cannot widen the band by more than this (each side)."""


# R23.3: Shares recommendation spine (eligibility + plan + sizing)
SHARES_NEAR_SUPPORT_PCT: float = 0.02
"""Symbol is 'near support' when distance_to_support_pct <= this (e.g. 2%)."""

SHARES_RISK_PCT_DEFAULT: float = 0.005
"""Default risk per trade for shares sizing (0.5% of account value)."""

SHARES_ALLOW_REGIME_NEUTRAL: bool = False
"""If True, shares eligible when regime is UP or NEUTRAL; else UP only."""

SHARES_ENTRY_ZONE_ATR_MULT: float = 0.25
"""Entry zone width (each side) as multiple of ATR."""

SHARES_STOP_ATR_MULT: float = 1.0
"""Stop distance below support as multiple of ATR."""

# R23.3 UAT only: force shares eligibility for these symbols (request-time only; not persisted).
# Comma-separated, e.g. "NVDA" or "NVDA,WMT". Override via env SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS for UAT.
SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS: str = ""
"""UAT-only: when non-empty, symbols in this list get shares_plan.eligible=true and reason_codes include SHARES_UAT_FORCED."""

# R23.4.5: Targets/exit plan validity — minimum distance for S/R levels to be used as targets
MIN_TARGET_DISTANCE_PCT: float = 0.002
"""Minimum distance (as fraction of spot) for resistance/support to be used as target. 0.002 = 0.20%. If no level meets this, use ATR fallback."""

TARGET_EPS_PCT: float = 0.001
"""Epsilon: level is considered 'at or past spot' when within this fraction of spot. 0.001 = 0.10%. Do not use resistance <= spot*(1+eps) or support >= spot*(1-eps)."""

# R24.0: Options position sizing (request-time only; not persisted)
OPTIONS_RISK_PCT_PER_TRADE_DEFAULT: float = 0.01
"""Default risk per trade for options sizing (1% of account value)."""

OPTIONS_MAX_CONTRACTS_PER_TRADE: int = 3
"""Maximum contracts per options trade (CSP/CC)."""

OPTIONS_MAX_NOTIONAL_PCT: float = 0.15
"""Maximum notional per trade as fraction of account (0.15 = 15%)."""


__all__ = [
    "CSP_MIN_DTE",
    "CSP_MAX_DTE",
    "CSP_TARGET_DELTA_LOW",
    "CSP_TARGET_DELTA_HIGH",
    "MAX_CAPITAL_PER_SYMBOL_PCT",
    "MIN_PRICE",
    "MAX_PRICE",
    "TARGET_LOW",
    "TARGET_HIGH",
    "DELTA_NEAR_MISS_EPS",
    "DELTA_OVERRIDE_MAX_WIDEN",
    "SHARES_NEAR_SUPPORT_PCT",
    "SHARES_RISK_PCT_DEFAULT",
    "SHARES_ALLOW_REGIME_NEUTRAL",
    "SHARES_ENTRY_ZONE_ATR_MULT",
    "SHARES_STOP_ATR_MULT",
    "SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS",
    "MIN_TARGET_DISTANCE_PCT",
    "TARGET_EPS_PCT",
    "OPTIONS_RISK_PCT_PER_TRADE_DEFAULT",
    "OPTIONS_MAX_CONTRACTS_PER_TRADE",
    "OPTIONS_MAX_NOTIONAL_PCT",
]
