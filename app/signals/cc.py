# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CC (Covered Call) signal generator."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import List

from app.core.market.stock_models import StockSnapshot
from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote
from app.signals.models import (
    CCConfig,
    ExclusionReason,
    ExplanationItem,
    SignalCandidate,
    SignalEngineConfig,
    SignalType,
)
from app.signals.utils import calc_dte, mid, spread_pct


def generate_cc_candidates(
    stock: StockSnapshot,
    options: List[NormalizedOptionQuote],
    cfg: CCConfig,
    base_cfg: SignalEngineConfig,
) -> tuple[List[SignalCandidate], List[ExclusionReason]]:
    """Generate CC signal candidates from stock snapshot and normalized options.

    Args:
        stock: Stock snapshot with underlying price
        options: List of normalized option quotes (should include CALLs)
        cfg: CC-specific configuration
        base_cfg: Base signal engine configuration

    Returns:
        Tuple of (candidates, exclusions)
        - candidates: List of SignalCandidate objects, sorted by expiry then strike
        - exclusions: List of ExclusionReason objects explaining why no candidates were found
    """
    candidates: List[SignalCandidate] = []
    exclusions: List[ExclusionReason] = []

    # Get underlying price
    underlying_price = stock.price
    if underlying_price is None:
        exclusions.append(
            ExclusionReason(
                code="NO_UNDERLYING_PRICE",
                message=f"No underlying price available for {stock.symbol}",
                data={"symbol": stock.symbol},
            )
        )
        return candidates, exclusions

    # Filter CALL options only
    call_options = [opt for opt in options if opt.right == "CALL" and opt.underlying.upper() == stock.symbol.upper()]

    if not call_options:
        exclusions.append(
            ExclusionReason(
                code="NO_OPTIONS_FOR_SYMBOL",
                message=f"No CALL options found for {stock.symbol}",
                data={"symbol": stock.symbol, "total_options": len(options)},
            )
        )
        return candidates, exclusions

    # Group by expiry and filter by DTE
    as_of = stock.snapshot_time
    expiry_groups: dict[date, List[NormalizedOptionQuote]] = defaultdict(list)

    for opt in call_options:
        dte = calc_dte(as_of, opt.expiry)
        if base_cfg.dte_min <= dte <= base_cfg.dte_max:
            expiry_groups[opt.expiry].append(opt)

    if not expiry_groups:
        exclusions.append(
            ExclusionReason(
                code="NO_EXPIRY_IN_DTE_WINDOW",
                message=f"No expirations in DTE window [{base_cfg.dte_min}, {base_cfg.dte_max}] for {stock.symbol}",
                data={
                    "symbol": stock.symbol,
                    "dte_min": base_cfg.dte_min,
                    "dte_max": base_cfg.dte_max,
                    "total_calls": len(call_options),
                },
            )
        )
        return candidates, exclusions

    # Process each expiry
    for expiry in sorted(expiry_groups.keys()):
        expiry_options = expiry_groups[expiry]

        # Filter by liquidity (bid, OI, spread)
        liquid_options: List[NormalizedOptionQuote] = []
        for opt in expiry_options:
            # Check bid
            if opt.bid is None or opt.bid < base_cfg.min_bid:
                continue

            # Check open interest
            if opt.open_interest is None or opt.open_interest < base_cfg.min_open_interest:
                continue

            # Check spread
            spread = spread_pct(opt.bid, opt.ask)
            if spread is None or spread > base_cfg.max_spread_pct:
                continue

            liquid_options.append(opt)

        if not liquid_options:
            exclusions.append(
                ExclusionReason(
                    code="NO_LIQUID_CALLS",
                    message=f"No liquid CALLs for {stock.symbol} expiry {expiry.isoformat()}",
                    data={
                        "symbol": stock.symbol,
                        "expiry": expiry.isoformat(),
                        "min_bid": base_cfg.min_bid,
                        "min_open_interest": base_cfg.min_open_interest,
                        "max_spread_pct": base_cfg.max_spread_pct,
                        "total_calls_for_expiry": len(expiry_options),
                    },
                )
            )
            continue

        # Filter by OTM percentage or delta range
        eligible_options: List[NormalizedOptionQuote] = []
        selection_path = None

        # Determine if we should use delta-based selection
        use_delta_selection = cfg.delta_min is not None and cfg.delta_max is not None

        for opt in liquid_options:
            strike_float = float(opt.strike)
            # For calls, OTM means strike > spot: OTM% = (strike - spot) / spot
            otm_pct = (strike_float - underlying_price) / underlying_price if underlying_price > 0 and strike_float > underlying_price else None

            if use_delta_selection:
                # Delta-based selection: require delta to be present and in range
                # For calls, delta is positive
                if opt.delta is not None:
                    if cfg.delta_min <= opt.delta <= cfg.delta_max:
                        eligible_options.append(opt)
                        if selection_path is None:
                            selection_path = "DELTA"
            else:
                # OTM percentage selection: strike must be > spot
                if otm_pct is not None and cfg.otm_pct_min <= otm_pct <= cfg.otm_pct_max:
                    eligible_options.append(opt)
                    if selection_path is None:
                        selection_path = "OTM_PCT"

        if not eligible_options:
            # Determine exclusion code based on selection method used
            if use_delta_selection:
                exclusion_code = "NO_STRIKES_IN_DELTA_RANGE"
            else:
                exclusion_code = "NO_STRIKES_IN_OTM_RANGE"
            
            exclusions.append(
                ExclusionReason(
                    code=exclusion_code,
                    message=f"No strikes in range for {stock.symbol} expiry {expiry.isoformat()}",
                    data={
                        "symbol": stock.symbol,
                        "expiry": expiry.isoformat(),
                        "underlying_price": underlying_price,
                        "otm_pct_min": cfg.otm_pct_min,
                        "otm_pct_max": cfg.otm_pct_max,
                        "delta_min": cfg.delta_min,
                        "delta_max": cfg.delta_max,
                        "selection_path": "DELTA" if use_delta_selection else "OTM_PCT",
                        "liquid_options_count": len(liquid_options),
                    },
                )
            )
            continue

        # Select one strike per expiry (deterministic: prefer higher strike, then higher bid)
        selected_opt = max(
            eligible_options,
            key=lambda o: (float(o.strike), o.bid or 0.0),
        )

        # Calculate derived values
        strike_float = float(selected_opt.strike)
        otm_pct = (strike_float - underlying_price) / underlying_price if underlying_price > 0 and strike_float > underlying_price else None
        mid_price = mid(selected_opt.bid, selected_opt.ask)
        spread = spread_pct(selected_opt.bid, selected_opt.ask)
        dte = calc_dte(as_of, expiry)

        # Build explanation items
        explanation_items: List[ExplanationItem] = [
            ExplanationItem(code="DTE", message=f"Days to expiration: {dte}", data={"dte": dte}),
            ExplanationItem(
                code="SPOT",
                message=f"Underlying price: ${underlying_price:.2f}",
                data={"spot": underlying_price},
            ),
            ExplanationItem(
                code="STRIKE",
                message=f"Strike: ${strike_float:.2f}",
                data={"strike": strike_float},
            ),
        ]

        if otm_pct is not None:
            explanation_items.append(
                ExplanationItem(
                    code="OTM_PCT",
                    message=f"OTM percentage: {otm_pct * 100:.2f}%",
                    data={"otm_pct": otm_pct},
                )
            )

        if spread is not None:
            explanation_items.append(
                ExplanationItem(
                    code="SPREAD_PCT",
                    message=f"Spread: {spread:.2f}%",
                    data={"spread_pct": spread},
                )
            )

        if selected_opt.bid is not None:
            explanation_items.append(
                ExplanationItem(code="BID", message=f"Bid: ${selected_opt.bid:.2f}", data={"bid": selected_opt.bid})
            )

        if selected_opt.ask is not None:
            explanation_items.append(
                ExplanationItem(code="ASK", message=f"Ask: ${selected_opt.ask:.2f}", data={"ask": selected_opt.ask})
            )

        if mid_price is not None:
            explanation_items.append(
                ExplanationItem(
                    code="MID",
                    message=f"Mid: ${mid_price:.2f}",
                    data={"mid": mid_price},
                )
            )

        if selected_opt.volume is not None:
            explanation_items.append(
                ExplanationItem(
                    code="VOLUME",
                    message=f"Volume: {selected_opt.volume}",
                    data={"volume": selected_opt.volume},
                )
            )

        if selected_opt.open_interest is not None:
            explanation_items.append(
                ExplanationItem(
                    code="OPEN_INTEREST",
                    message=f"Open Interest: {selected_opt.open_interest}",
                    data={"open_interest": selected_opt.open_interest},
                )
            )

        if selection_path:
            explanation_items.append(
                ExplanationItem(
                    code="SELECTION_PATH",
                    message=f"Selection method: {selection_path}",
                    data={"selection_path": selection_path},
                )
            )

        # Create candidate
        candidate = SignalCandidate(
            symbol=stock.symbol,
            signal_type=SignalType.CC,
            as_of=as_of,
            underlying_price=underlying_price,
            expiry=expiry,
            strike=strike_float,
            option_right="CALL",
            bid=selected_opt.bid,
            ask=selected_opt.ask,
            mid=mid_price,
            volume=selected_opt.volume,
            open_interest=selected_opt.open_interest,
            delta=selected_opt.delta,
            iv=selected_opt.iv,
            explanation=explanation_items,
        )
        candidates.append(candidate)

    # Sort candidates deterministically: expiry, then strike
    candidates.sort(key=lambda c: (c.expiry, c.strike))

    return candidates, exclusions


__all__ = ["generate_cc_candidates"]
