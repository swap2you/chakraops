# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.8: Batch Planner — process symbols in predictable chunks.

Stable ordering, deterministic. Used by evaluation runner to cap concurrency.
"""

from __future__ import annotations

from typing import List


def plan_batches(symbols: List[str], batch_size: int) -> List[List[str]]:
    """
    Split symbols into batches of up to batch_size.
    Stable ordering, deterministic. Empty input -> empty list.
    """
    if not symbols or batch_size <= 0:
        return []
    batches: List[List[str]] = []
    for i in range(0, len(symbols), batch_size):
        batches.append(symbols[i : i + batch_size])
    return batches
