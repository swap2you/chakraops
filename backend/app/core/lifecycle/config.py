# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.0: Hybrid Exit Model config. Informational only; no trading logic."""

from __future__ import annotations

# Premium targets (decimal; e.g. 0.60 = 60%)
PREMIUM_BASE_TARGET_PCT = 0.60
PREMIUM_EXTENSION_TARGET_PCT = 0.75

# DTE thresholds (days)
DTE_SOFT_EXIT_THRESHOLD = 14
DTE_HARD_EXIT_THRESHOLD = 7

# Regime / panic
PANIC_REGIME_FLIP_ENABLED = True
PANIC_ATR_MULT = 1.5

# Structure extension above resistance (CSP) / below support (CC)
STRUCTURE_EXTENSION_ENABLED = True
