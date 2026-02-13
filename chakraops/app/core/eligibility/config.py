# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Eligibility gate thresholds. Single source of truth."""

from __future__ import annotations

# Support / resistance proximity (as fraction of price; e.g. 0.02 = 2%)
SUPPORT_NEAR_PCT = 0.02
RESIST_NEAR_PCT = 0.02

# RSI bounds (Phase 4.2: entry proximity)
CSP_RSI_MIN = 40.0
CSP_RSI_MAX = 60.0
CC_RSI_MIN = 50.0
CC_RSI_MAX = 65.0

# ATR% cap
MAX_ATR_PCT = 0.05

# Indicator periods
RSI_PERIOD = 14
EMA_FAST = 20
EMA_MID = 50
EMA_SLOW = 200
ATR_PERIOD = 14
SWING_LOOKBACK = 30
EMA_SLOPE_MIN = 1e-6

# Phase 5.0: Support/Resistance — swing-cluster (fractal + ATR clustering)
SWING_CLUSTER_WINDOW = 90
SWING_FRACTAL_K = 3
S_R_ATR_MULT = 0.5
S_R_PCT_TOL = 0.006
# Phase 5.0.1: Hard-cap tolerance (max fraction of spot)
MAX_S_R_TOL_PCT = 0.012
