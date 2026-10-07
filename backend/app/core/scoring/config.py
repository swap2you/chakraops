# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.1: Scoring config. Diagnostic only; does not change mode_decision or Stage-2."""

from __future__ import annotations

# Account / position sizing (informational)
ACCOUNT_EQUITY_DEFAULT = 150_000
MAX_CONTRACTS_PER_SYMBOL = 5
MAX_NOTIONAL_PCT_PER_TRADE = 0.20  # e.g. 20% of account on one CSP
MAX_TOTAL_NOTIONAL_PCT = 0.60  # total capital across all positions (informational)
MIN_FREE_CASH_PCT = 0.10  # keep 10% cash buffer (informational)
DEFAULT_RISK_MODE = "CONSERVATIVE"  # optional; no complexity added

# Affordability score: 100 at notional_pct <= AFFORDABILITY_PCT_100, 0 at >= AFFORDABILITY_PCT_0
AFFORDABILITY_PCT_100 = 0.05   # <= 5% of account -> score 100
AFFORDABILITY_PCT_0 = 0.30     # >= 30% of account -> score 0

# Tier thresholds (assign_tier)
TIER_A_MIN = 80   # A: composite_score >= 80
TIER_B_MIN = 60   # B: 60 <= score < 80
TIER_C_MIN = 40   # C: 40 <= score < 60
# NONE: mode_decision==NONE or score < 40

# Phase 6.3: Alert severity (informational only)
SEVERITY_READY_PCT = 0.015   # 1.5% — within this distance -> READY (tier A/B)
SEVERITY_NOW_PCT = 0.0075    # 0.75% — within this distance + tier A -> NOW

# Component weights for composite_score (must sum to 1.0)
SCORE_WEIGHTS = {
    "regime": 0.20,
    "rsi": 0.15,
    "sr_proximity": 0.20,
    "vol": 0.15,
    "liquidity": 0.15,
    "affordability": 0.15,
}
