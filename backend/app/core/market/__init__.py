# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2 market primitives.

This package is intentionally small and deterministic:
- Defines the internal stock snapshot data contract (Phase 2)
- Defines the curated stock universe manager (Phase 2)

Phase 3+ (CSP/CC logic, scoring, UI) must consume these contracts, but is OUT OF
SCOPE for this phase.
"""

from .stock_models import StockSnapshot
from .stock_universe import StockUniverseManager

__all__ = ["StockSnapshot", "StockUniverseManager"]

