# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2: Internal stock snapshot data contract (deterministic).

IMPORTANT:
- This is NOT strategy logic.
- This model must not apply filtering or tradability checks.
- Missing fields must be None (never throw).
- Zero values are allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass(frozen=True)
class StockSnapshot:
    """Single internal stock snapshot structure for ChakraOps Phase 2+."""

    symbol: str
    price: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    volume: Optional[int]
    has_options: bool
    snapshot_time: datetime
    data_source: Literal["ORATS", "SNAPSHOT", "YFINANCE"]
    avg_option_volume_20d: Optional[float] = None
    avg_stock_volume_20d: Optional[float] = None


__all__ = ["StockSnapshot"]

