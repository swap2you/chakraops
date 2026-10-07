# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.2: Realized PnL for options — explicit position_side (SHORT/LONG) and option_side (PUT/CALL).

Convention: All amounts are in total dollars (not per-share). Caller must pass:
- SHORT: entry_credit_total (premium received at open), close_debit_total (cost to buy back).
- LONG: entry_debit_total (cost to open), close_credit_total (premium received at close).

Fees: open_fees and close_fees are subtracted from realized when provided (fees are modeled).
"""

from __future__ import annotations


def compute_realized_pnl_short_option(
    entry_credit_total: float,
    close_debit_total: float,
    open_fees: float = 0.0,
    close_fees: float = 0.0,
) -> float:
    """
    SHORT option (sold): profit when credit at open > debit at close.
    realized = entry_credit - close_debit - open_fees - close_fees.
    Example: entry 9.40/share * 100 = 940, close 4.50/share * 100 = 450 → 490 (1 contract).
    """
    return round(
        float(entry_credit_total) - float(close_debit_total)
        - float(open_fees) - float(close_fees),
        2,
    )


def compute_realized_pnl_long_option(
    entry_debit_total: float,
    close_credit_total: float,
    open_fees: float = 0.0,
    close_fees: float = 0.0,
) -> float:
    """
    LONG option (bought): profit when close credit > entry debit.
    realized = close_credit - entry_debit - open_fees - close_fees.
    """
    return round(
        float(close_credit_total) - float(entry_debit_total)
        - float(open_fees) - float(close_fees),
        2,
    )


def compute_realized_pnl(
    position_side: str,
    entry_credit_total: float | None,
    close_debit_total: float | None,
    entry_debit_total: float | None,
    close_credit_total: float | None,
    open_fees: float = 0.0,
    close_fees: float = 0.0,
) -> float | None:
    """
    Single entry point: dispatch by position_side.
    SHORT: needs entry_credit_total, close_debit_total (others ignored).
    LONG: needs entry_debit_total, close_credit_total (others ignored).
    Returns None if required values are missing.
    """
    side = (position_side or "").strip().upper()
    if side == "SHORT":
        if entry_credit_total is None or close_debit_total is None:
            return None
        return compute_realized_pnl_short_option(
            entry_credit_total, close_debit_total, open_fees, close_fees
        )
    if side == "LONG":
        if entry_debit_total is None or close_credit_total is None:
            return None
        return compute_realized_pnl_long_option(
            entry_debit_total, close_credit_total, open_fees, close_fees
        )
    return None


def normalize_open_credit_to_total(
    open_credit: float | None,
    contracts: int,
    *,
    per_share_threshold: float = 100.0,
) -> float | None:
    """
    If open_credit looks like per-share premium (0 < value < per_share_threshold), convert to total dollars.
    Otherwise treat as total. Returns None if open_credit is None or <= 0.
    Avoids double-multiplication by 100 when caller already stores total.
    """
    if open_credit is None or open_credit <= 0 or contracts <= 0:
        return None
    val = float(open_credit)
    if 0 < val < per_share_threshold:
        return val * 100 * contracts
    return val
