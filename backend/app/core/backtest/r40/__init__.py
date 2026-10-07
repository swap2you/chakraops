# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 Strategy Lab research lane: metrics, fills, walk-forward (SIMULATION only).

Parallel to R27.5 journal backtest — does not replace or rewrite it.
Offline / fixture-driven; no broker writes; no live ORATS hist required for unit tests.
"""

from __future__ import annotations

from app.core.backtest.r40.fills import FillAssumptions, premium_fill
from app.core.backtest.r40.metrics import TradeRecord, compute_metrics
from app.core.backtest.r40.walk_forward import WalkForwardResult, run_walk_forward

__all__ = [
    "FillAssumptions",
    "TradeRecord",
    "WalkForwardResult",
    "compute_metrics",
    "premium_fill",
    "run_walk_forward",
]
