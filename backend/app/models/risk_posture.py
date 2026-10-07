# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Risk posture for execution and sizing (Phase 4.5.5).

Scaffold: currently locked to CONSERVATIVE. Future: BALANCED/AGGRESSIVE
may relax thresholds (e.g. min_trading_days_to_expiry, earnings_block_window_days).
"""

from __future__ import annotations

from enum import Enum


class RiskPosture(str, Enum):
    """Risk posture level. Locked to CONSERVATIVE in Phase 4.5.5."""

    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"
