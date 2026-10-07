# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.9: Request cost model — estimate calls per symbol for budgeting.

Used only for budgeting + warnings. Not enforced by provider.
"""

from __future__ import annotations

from typing import List

REQUEST_COST = {
    "cores": 1,
    "strikes": 1,
    "iv_rank": 1,
}

DEFAULT_REQUESTS_PER_SYMBOL = 3


def estimate_requests_for_symbols(
    symbols: List[str],
    endpoints_used: List[str] | None = None,
) -> int:
    """
    Estimate total HTTP requests for given symbols and endpoints.
    If endpoints_used omitted, uses default model (cores + strikes + iv_rank).
    """
    n = len(symbols)
    if n <= 0:
        return 0
    if endpoints_used:
        cost_per = sum(REQUEST_COST.get(e.strip().lower(), 1) for e in endpoints_used)
    else:
        cost_per = sum(REQUEST_COST.values()) if REQUEST_COST else DEFAULT_REQUESTS_PER_SYMBOL
    return n * cost_per
