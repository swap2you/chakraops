# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Risk override configuration constants.

This module contains configuration values for risk management overrides.
These are pure constants with no business logic.

All values are subject to change based on risk management strategy refinement.
"""

from __future__ import annotations

# RISK_OFF regime handling
RISK_OFF_CLOSE_ENABLED: bool = False
"""Enable automatic CLOSE action when RISK_OFF regime is detected.

If True, positions in OPEN state will be automatically closed when
market regime is RISK_OFF. If False, an ALERT will be raised instead.
"""

# Drawdown thresholds
PANIC_DRAWDOWN_PCT: float = 0.10
"""Panic drawdown threshold as a percentage.

If position drawdown exceeds this percentage (10% by default),
an ALERT (HIGH) will be raised. Expressed as a decimal (0.10 = 10%).
"""

# EMA200 break threshold
EMA200_BREAK_PCT: float = 0.02
"""EMA200 break threshold as a percentage.

If current price falls below EMA200 * (1 - EMA200_BREAK_PCT),
an ALERT (HIGH) will be raised. Expressed as a decimal (0.02 = 2%).
"""


__all__ = [
    "RISK_OFF_CLOSE_ENABLED",
    "PANIC_DRAWDOWN_PCT",
    "EMA200_BREAK_PCT",
]
