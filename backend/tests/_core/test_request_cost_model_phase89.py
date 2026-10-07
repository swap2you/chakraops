# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.9: Request cost model."""

from __future__ import annotations

import pytest

from app.core.eval.request_cost_model import estimate_requests_for_symbols


def test_estimate_requests_for_symbols():
    """estimate_requests_for_symbols computes requests from symbols and endpoints."""
    # cores=1, strikes=1, iv_rank=1 -> cost_per=3
    symbols = ["AAPL", "MSFT", "GOOGL"]
    endpoints = ["cores", "strikes", "iv_rank"]
    assert estimate_requests_for_symbols(symbols, endpoints) == 9  # 3 * 3

    # Single endpoint
    assert estimate_requests_for_symbols(symbols, ["cores"]) == 3

    # Default endpoints (cores+strikes+iv_rank)
    assert estimate_requests_for_symbols(symbols) == 9

    # Empty symbols
    assert estimate_requests_for_symbols([], endpoints) == 0
    assert estimate_requests_for_symbols([], []) == 0
