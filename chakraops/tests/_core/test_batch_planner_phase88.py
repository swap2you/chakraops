# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.8: Batch Planner."""

from __future__ import annotations

import pytest

from app.core.eval.batch_planner import plan_batches


def test_plan_batches_stable():
    """plan_batches produces stable, deterministic ordering."""
    symbols = ["A", "B", "C", "D", "E", "F"]
    b1 = plan_batches(symbols, 2)
    b2 = plan_batches(symbols, 2)
    assert b1 == b2
    assert b1 == [["A", "B"], ["C", "D"], ["E", "F"]]


def test_plan_batches_exact_sizes():
    """plan_batches respects batch_size; last batch may be smaller."""
    symbols = list("ABCDEFGH")
    batches = plan_batches(symbols, 3)
    assert len(batches) == 3
    assert batches[0] == ["A", "B", "C"]
    assert batches[1] == ["D", "E", "F"]
    assert batches[2] == ["G", "H"]
    assert sum(len(b) for b in batches) == 8
