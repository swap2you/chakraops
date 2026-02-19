# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.2: Unit tests for realized PnL — SHORT/LONG formulas and normalization."""

from __future__ import annotations

import pytest

from app.core.positions.realized_pnl import (
    compute_realized_pnl_short_option,
    compute_realized_pnl_long_option,
    compute_realized_pnl,
    normalize_open_credit_to_total,
)


# ---------------------------------------------------------------------------
# SHORT option (Phase 21.2: entry_credit=9.40/share, close_debit=4.50/share → +$490 per contract)
# ---------------------------------------------------------------------------


def test_short_put_realized_positive_per_contract():
    """SHORT PUT: entry 9.40/share * 100 = 940, close 4.50/share * 100 = 450 → +490 (1 contract)."""
    entry_total = 9.40 * 100  # 940
    close_total = 4.50 * 100  # 450
    r = compute_realized_pnl_short_option(entry_total, close_total, 0.0, 0.0)
    assert r == 490.0


def test_short_put_realized_with_fees():
    """SHORT: 940 - 450 - 2 - 1 = 487."""
    r = compute_realized_pnl_short_option(940.0, 450.0, 2.0, 1.0)
    assert r == 487.0


def test_short_put_realized_via_compute_realized_pnl():
    """Dispatch SHORT: same 9.40/4.50 → 490."""
    r = compute_realized_pnl(
        "SHORT",
        entry_credit_total=940.0,
        close_debit_total=450.0,
        entry_debit_total=None,
        close_credit_total=None,
    )
    assert r == 490.0


# ---------------------------------------------------------------------------
# LONG option
# ---------------------------------------------------------------------------


def test_long_option_realized_positive():
    """LONG: close_credit 500, entry_debit 400 → +100."""
    r = compute_realized_pnl_long_option(400.0, 500.0, 0.0, 0.0)
    assert r == 100.0


def test_long_option_realized_via_compute_realized_pnl():
    """Dispatch LONG: entry_debit 400, close_credit 500 → 100."""
    r = compute_realized_pnl(
        "LONG",
        entry_credit_total=None,
        close_debit_total=None,
        entry_debit_total=400.0,
        close_credit_total=500.0,
    )
    assert r == 100.0


def test_long_option_realized_negative_when_close_less_than_entry():
    """LONG: close 300, entry 400 → -100."""
    r = compute_realized_pnl_long_option(400.0, 300.0, 0.0, 0.0)
    assert r == -100.0


# ---------------------------------------------------------------------------
# Normalization: per-share vs total
# ---------------------------------------------------------------------------


def test_normalize_per_share_to_total():
    """9.40 per share, 1 contract → 940 total."""
    t = normalize_open_credit_to_total(9.40, 1)
    assert t == 940.0


def test_normalize_per_share_two_contracts():
    """9.40 per share, 2 contracts → 1880."""
    t = normalize_open_credit_to_total(9.40, 2)
    assert t == 1880.0


def test_normalize_treats_large_as_total():
    """250 (total) stays 250 (no * 100 * contracts)."""
    t = normalize_open_credit_to_total(250.0, 1)
    assert t == 250.0


def test_normalize_none_or_zero_returns_none():
    assert normalize_open_credit_to_total(None, 1) is None
    assert normalize_open_credit_to_total(0.0, 1) is None
    assert normalize_open_credit_to_total(9.40, 0) is None


# ---------------------------------------------------------------------------
# Regression: portfolio realized total = sum of position realized
# (Tested implicitly via close flow; here we ensure formula is deterministic.)
# ---------------------------------------------------------------------------


def test_short_realized_deterministic():
    """Same inputs always give same output."""
    a = compute_realized_pnl_short_option(940.0, 450.0, 0.0, 0.0)
    b = compute_realized_pnl_short_option(940.0, 450.0, 0.0, 0.0)
    assert a == b == 490.0
