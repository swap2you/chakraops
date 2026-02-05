# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Adapter to normalize Theta options chain data to internal format."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.signals.models import ExclusionReason


@dataclass(frozen=True)
class NormalizedOptionQuote:
    """Immutable normalized option quote from chain data (Theta or ORATS)."""

    underlying: str
    expiry: date
    strike: Decimal
    right: str  # "PUT" or "CALL"
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    as_of: datetime
    iv: Optional[float] = None
    delta: Optional[float] = None
    prob_otm: Optional[float] = None  # Probability OTM (0–1), from ORATS when available
    iv_rank: Optional[float] = None   # IV rank, from ORATS when available

    def __post_init__(self) -> None:
        """Validate right field."""
        if self.right not in ("PUT", "CALL"):
            raise ValueError(f"right must be PUT or CALL, got {self.right}")


def normalize_theta_chain(
    theta_chain: List[Dict[str, Any]],
    as_of: datetime,
    underlying: Optional[str] = None,
) -> tuple[List[NormalizedOptionQuote], List[ExclusionReason]]:
    """Normalize Theta options chain data to internal format.

    Args:
        theta_chain: List of option contract dictionaries from Theta API
        as_of: Timestamp for when this data was captured
        underlying: Underlying symbol (extracted from chain if not provided)

    Returns:
        Tuple of (normalized_quotes, exclusions)
        - normalized_quotes: Successfully parsed and normalized quotes
        - exclusions: Reasons why rows were excluded (unparseable fields)

    Notes:
        - Required fields: expiry, strike, right
        - Optional fields: bid, ask, last, volume, open_interest, iv, delta
        - Missing required fields result in ExclusionReason with code UNPARSABLE_OPTION_ROW
        - No liquidity filtering is applied (only parsing normalization)
    """
    normalized: List[NormalizedOptionQuote] = []
    exclusions: List[ExclusionReason] = []

    for idx, row in enumerate(theta_chain):
        if not isinstance(row, dict):
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} is not a dictionary",
                    data={"row_index": idx, "row_type": type(row).__name__},
                )
            )
            continue

        # Extract underlying symbol (from row or parameter)
        underlying_symbol = underlying or row.get("symbol") or row.get("underlying")
        if not underlying_symbol:
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} missing underlying symbol",
                    data={"row_index": idx, "raw_row_keys": list(row.keys())},
                )
            )
            continue

        # Parse expiry (required)
        expiry = None
        expiry_raw = row.get("expiry") or row.get("expiration") or row.get("exp")
        if expiry_raw:
            try:
                if isinstance(expiry_raw, date):
                    expiry = expiry_raw
                elif isinstance(expiry_raw, str):
                    # Try ISO format (YYYY-MM-DD)
                    if len(expiry_raw) == 10 and expiry_raw.count("-") == 2:
                        year, month, day = map(int, expiry_raw.split("-"))
                        expiry = date(year, month, day)
                    # Try YYYYMMDD format
                    elif len(expiry_raw) == 8 and expiry_raw.isdigit():
                        expiry = date(
                            int(expiry_raw[:4]),
                            int(expiry_raw[4:6]),
                            int(expiry_raw[6:8]),
                        )
            except (ValueError, TypeError, AttributeError):
                pass

        if expiry is None:
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} missing or unparseable expiry",
                    data={
                        "row_index": idx,
                        "expiry_raw": expiry_raw,
                        "raw_row_keys": list(row.keys()),
                    },
                )
            )
            continue

        # Parse strike (required)
        strike = None
        strike_raw = row.get("strike") or row.get("strike_price")
        if strike_raw is not None:
            try:
                strike = Decimal(str(strike_raw))
            except (ValueError, TypeError, ArithmeticError):
                pass

        if strike is None:
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} missing or unparseable strike",
                    data={
                        "row_index": idx,
                        "strike_raw": strike_raw,
                        "raw_row_keys": list(row.keys()),
                    },
                )
            )
            continue

        # Parse right (required)
        right_raw = row.get("right") or row.get("option_type") or row.get("type")
        if right_raw:
            right_upper = str(right_raw).upper()
            # Normalize common variations
            if right_upper in ("P", "PUT", "PUTS"):
                right = "PUT"
            elif right_upper in ("C", "CALL", "CALLS"):
                right = "CALL"
            else:
                right = None
        else:
            right = None

        if right is None:
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} missing or unparseable right",
                    data={
                        "row_index": idx,
                        "right_raw": right_raw,
                        "raw_row_keys": list(row.keys()),
                    },
                )
            )
            continue

        # Parse optional fields (gracefully handle missing/None)
        def _parse_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def _parse_int(val: Any) -> Optional[int]:
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        bid = _parse_float(row.get("bid") or row.get("bid_price"))
        ask = _parse_float(row.get("ask") or row.get("ask_price"))
        last = _parse_float(row.get("last") or row.get("last_price") or row.get("close"))
        volume = _parse_int(row.get("volume") or row.get("vol"))
        open_interest = _parse_int(row.get("open_interest") or row.get("oi") or row.get("openInterest"))
        iv = _parse_float(row.get("iv") or row.get("implied_vol") or row.get("implied_volatility"))
        delta = _parse_float(row.get("delta"))
        prob_otm = _parse_float(row.get("prob_otm") or row.get("probOTM") or (row.get("putProbOtm") if right == "PUT" else row.get("callProbOtm")))
        iv_rank = _parse_float(row.get("iv_rank") or row.get("iv_rank_100_day") or row.get("ivRank100d") or row.get("iv_percentile"))

        # Create normalized quote
        try:
            quote = NormalizedOptionQuote(
                underlying=str(underlying_symbol).upper(),
                expiry=expiry,
                strike=strike,
                right=right,
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
                open_interest=open_interest,
                iv=iv,
                delta=delta,
                prob_otm=prob_otm,
                iv_rank=iv_rank,
                as_of=as_of,
            )
            normalized.append(quote)
        except ValueError as e:
            exclusions.append(
                ExclusionReason(
                    code="UNPARSABLE_OPTION_ROW",
                    message=f"Row {idx} validation failed: {e}",
                    data={
                        "row_index": idx,
                        "validation_error": str(e),
                        "raw_row_keys": list(row.keys()),
                    },
                )
            )

    # Sort normalized quotes deterministically: (expiry, strike, right)
    normalized.sort(key=lambda q: (q.expiry, q.strike, q.right))

    return normalized, exclusions


__all__ = [
    "NormalizedOptionQuote",
    "normalize_theta_chain",
]
