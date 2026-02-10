# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Single contract validator for equity snapshots.

This is the ONLY module that performs:
- Instrument type classification (EQUITY / ETF / INDEX)
- Required-field resolution (instrument-specific)
- Derived field promotion (bid/ask from mid or single quote)
- Data completeness and missing-fields list

Consumers (staged_evaluator, API, CLI) must validate via this module so there is
no duplicated "missing fields" or required-field logic. Stage1Result is built from
ContractValidationResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.data.orats_client import FullEquitySnapshot
from app.core.data.instrument_type import (
    InstrumentType,
    classify_instrument,
    get_required_fields_for_instrument,
)
from app.core.data.derived_fields import derive_equity_fields
from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness_required,
)


@dataclass
class ContractValidationResult:
    """
    Canonical result of validating an equity snapshot against the data contract.
    Used to build Stage1Result; no duplicate required/missing logic elsewhere.
    """
    symbol: str
    instrument_type: InstrumentType

    # Resolved values (after derivation)
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    iv_rank: Optional[float] = None
    quote_date: Optional[str] = None

    # Completeness and diagnostics
    data_completeness: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    data_quality_details: Dict[str, str] = field(default_factory=dict)
    field_sources: Dict[str, str] = field(default_factory=dict)

    # Raw field quality (for downstream that need per-field reason)
    field_quality: Dict[str, FieldValue] = field(default_factory=dict)


def validate_equity_snapshot(symbol: str, snapshot: FullEquitySnapshot) -> ContractValidationResult:
    """
    Validate an ORATS equity snapshot: instrument type, required fields, derivations.
    Single source of truth for "what is required" and "what is missing".

    Args:
        symbol: Ticker symbol (for instrument classification).
        snapshot: FullEquitySnapshot from orats_client (e.g. fetch_full_equity_snapshots).

    Returns:
        ContractValidationResult with resolved values, completeness, missing_fields,
        and field_sources (ORATS | DERIVED) for building Stage1Result.
    """
    inst = classify_instrument(symbol)
    required_by_inst = get_required_fields_for_instrument(inst)
    # Stage 1 / data_quality use "quote_time" internally; API exposes "quote_date"
    required_keys = tuple(
        "quote_time" if k == "quote_date" else k for k in required_by_inst
    )

    result = ContractValidationResult(symbol=symbol, instrument_type=inst)

    raw_price = snapshot.price
    raw_bid = snapshot.bid
    raw_ask = snapshot.ask
    raw_volume = snapshot.volume
    raw_iv_rank = snapshot.iv_rank

    # Build field quality for required fields only (quote_time from quote_date)
    field_quality: Dict[str, FieldValue] = {}
    field_quality["price"] = wrap_field_float(raw_price, "price")
    field_quality["bid"] = wrap_field_float(raw_bid, "bid")
    field_quality["ask"] = wrap_field_float(raw_ask, "ask")
    field_quality["volume"] = wrap_field_int(raw_volume, "volume")
    if snapshot.quote_date is None:
        quote_time_fv = FieldValue(
            value=None,
            quality=DataQuality.MISSING,
            reason="quote_date not provided by source",
            field_name="quote_time",
        )
    else:
        quote_time_fv = FieldValue(
            value=snapshot.quote_date,
            quality=DataQuality.VALID,
            reason="",
            field_name="quote_time",
        )
    field_quality["quote_time"] = quote_time_fv
    field_quality["iv_rank"] = wrap_field_float(raw_iv_rank, "iv_rank")

    # Derive bid/ask when missing but derivable
    derived = derive_equity_fields(
        price=raw_price, bid=raw_bid, ask=raw_ask, volume=raw_volume,
    )
    for fname, eff_val in (("bid", derived.synthetic_bid), ("ask", derived.synthetic_ask)):
        if fname in field_quality and not field_quality[fname].is_valid and eff_val is not None:
            field_quality[fname] = FieldValue(
                value=eff_val,
                quality=DataQuality.VALID,
                reason="derived (single quote or mid)",
                field_name=fname,
            )

    # Per-field source: ORATS by default; DERIVED where we promoted
    result.field_sources = {k: "ORATS" for k in field_quality}
    if derived.sources:
        for f in ("bid", "ask"):
            if field_quality.get(f) and "derived" in (field_quality[f].reason or "").lower():
                result.field_sources[f] = "DERIVED"

    # Completeness over instrument-specific required keys
    result.data_completeness, missing_required = compute_data_completeness_required(
        field_quality, required_keys
    )
    result.missing_fields = [
        "quote_date" if name == "quote_time" else name for name in missing_required
    ]
    for name, fv in field_quality.items():
        result.data_quality_details[name] = str(fv.quality)

    result.field_quality = field_quality

    # Resolved values for Stage1Result
    result.price = field_quality["price"].value if field_quality["price"].is_valid else None
    result.bid = field_quality["bid"].value if field_quality["bid"].is_valid else None
    result.ask = field_quality["ask"].value if field_quality["ask"].is_valid else None
    result.volume = field_quality["volume"].value if field_quality["volume"].is_valid else None
    result.iv_rank = field_quality["iv_rank"].value if field_quality["iv_rank"].is_valid else None
    result.quote_date = snapshot.quote_date

    return result
