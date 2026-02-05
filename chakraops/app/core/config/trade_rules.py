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
]
