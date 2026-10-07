# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Iron Condor signal generator (Phase 4.2).

Builds bull put spread + bear call spread, same expiry. Rejects if either leg invalid.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, List, Optional

from app.core.market.stock_models import StockSnapshot
from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote
from app.signals.models import ExclusionReason, SignalEngineConfig
from app.signals.utils import calc_dte, mid, spread_pct


# Allowed spread widths (points) for iron condor legs
IC_SPREAD_WIDTHS = (1, 2, 5)


@dataclass(frozen=True)
class IronCondorCandidate:
    """Single iron condor: bull put spread + bear call spread, same expiry."""

    symbol: str
    expiry: date
    put_short_strike: float
    put_long_strike: float
    call_short_strike: float
    call_long_strike: float
    credit_put: float
    credit_call: float
    max_loss_put: float
    max_loss_call: float
    underlying_price: float
    option_context: Any = None

    @property
    def total_credit(self) -> float:
        return self.credit_put + self.credit_call

    @property
    def combined_max_loss(self) -> float:
        return max(self.max_loss_put, self.max_loss_call)

    @property
    def total_width(self) -> float:
        """Total width between short strikes (call_short - put_short)."""
        return self.call_short_strike - self.put_short_strike


def generate_iron_condor_candidates(
    stock: StockSnapshot,
    options: List[NormalizedOptionQuote],
    base_cfg: SignalEngineConfig,
    option_context: Any = None,
) -> tuple[List[IronCondorCandidate], List[ExclusionReason]]:
    """Generate iron condor candidates: bull put spread + bear call spread, same expiry.

    Groups options by expiry; for each expiry builds one IC when both legs are valid.
    Rejects if either leg invalid (no liquidity, negative credit, etc.).
    """
    candidates: List[IronCondorCandidate] = []
    exclusions: List[ExclusionReason] = []

    underlying_price = stock.price
    if underlying_price is None or underlying_price <= 0:
        exclusions.append(
            ExclusionReason(
                code="NO_UNDERLYING_PRICE",
                message=f"No underlying price for {stock.symbol}",
                data={"symbol": stock.symbol},
            )
        )
        return candidates, exclusions

    symbol_upper = stock.symbol.upper()
    as_of = stock.snapshot_time

    # Group by expiry: PUTs and CALLs per expiry
    puts_by_expiry: dict[date, List[NormalizedOptionQuote]] = defaultdict(list)
    calls_by_expiry: dict[date, List[NormalizedOptionQuote]] = defaultdict(list)

    for opt in options:
        if opt.underlying.upper() != symbol_upper:
            continue
        dte = calc_dte(as_of, opt.expiry)
        if not (base_cfg.dte_min <= dte <= base_cfg.dte_max):
            continue
        if opt.right == "PUT":
            puts_by_expiry[opt.expiry].append(opt)
        elif opt.right == "CALL":
            calls_by_expiry[opt.expiry].append(opt)

    expiries_with_both = sorted(set(puts_by_expiry.keys()) & set(calls_by_expiry.keys()))

    for expiry in expiries_with_both:
        expiry_puts = puts_by_expiry[expiry]
        expiry_calls = calls_by_expiry[expiry]

        # Liquid puts: bid >= min_bid, spread ok
        liquid_puts: List[NormalizedOptionQuote] = []
        for opt in expiry_puts:
            if opt.bid is None or opt.bid < base_cfg.min_bid:
                continue
            if opt.open_interest is not None and opt.open_interest < base_cfg.min_open_interest:
                continue
            sp = spread_pct(opt.bid, opt.ask)
            if sp is not None and sp > base_cfg.max_spread_pct:
                continue
            liquid_puts.append(opt)

        # Liquid calls
        liquid_calls: List[NormalizedOptionQuote] = []
        for opt in expiry_calls:
            if opt.bid is None or opt.bid < base_cfg.min_bid:
                continue
            if opt.open_interest is not None and opt.open_interest < base_cfg.min_open_interest:
                continue
            sp = spread_pct(opt.bid, opt.ask)
            if sp is not None and sp > base_cfg.max_spread_pct:
                continue
            liquid_calls.append(opt)

        if not liquid_puts or not liquid_calls:
            exclusions.append(
                ExclusionReason(
                    code="IC_NO_LIQUID_LEGS",
                    message=f"Iron condor: no liquid puts or calls for {stock.symbol} {expiry}",
                    data={
                        "symbol": stock.symbol,
                        "expiry": expiry.isoformat(),
                        "liquid_puts": len(liquid_puts),
                        "liquid_calls": len(liquid_calls),
                    },
                )
            )
            continue

        # Puts: strike < underlying (OTM puts). Sort by strike desc; we want short put just below ATM, long put lower.
        puts_below = sorted(
            [p for p in liquid_puts if float(p.strike) < underlying_price],
            key=lambda p: float(p.strike),
            reverse=True,
        )
        # Calls: strike > underlying (OTM calls). Sort by strike asc; we want short call just above ATM, long call higher.
        calls_above = sorted(
            [c for c in liquid_calls if float(c.strike) > underlying_price],
            key=lambda c: float(c.strike),
        )

        if len(puts_below) < 2 or len(calls_above) < 2:
            exclusions.append(
                ExclusionReason(
                    code="IC_INSUFFICIENT_STRIKES",
                    message=f"Iron condor: need 2+ puts below and 2+ calls above spot for {stock.symbol} {expiry}",
                    data={
                        "symbol": stock.symbol,
                        "expiry": expiry.isoformat(),
                        "puts_below": len(puts_below),
                        "calls_above": len(calls_above),
                    },
                )
            )
            continue

        # Build bull put spread: short put (higher strike), long put (lower strike). Width from IC_SPREAD_WIDTHS.
        put_short_opt: Optional[NormalizedOptionQuote] = None
        put_long_opt: Optional[NormalizedOptionQuote] = None
        best_put_credit: Optional[float] = None

        for width in IC_SPREAD_WIDTHS:
            for i, short_put in enumerate(puts_below):
                short_strike = float(short_put.strike)
                long_strike = short_strike - width
                long_put = next((p for p in puts_below if float(p.strike) == long_strike), None)
                if long_put is None:
                    continue
                mid_short = mid(short_put.bid, short_put.ask)
                mid_long = mid(long_put.bid, long_put.ask)
                if mid_short is None or mid_long is None:
                    continue
                credit_put = (mid_short - mid_long) * 100
                if credit_put <= 0:
                    continue
                if best_put_credit is None or credit_put > best_put_credit:
                    best_put_credit = credit_put
                    put_short_opt = short_put
                    put_long_opt = long_put

        if put_short_opt is None or put_long_opt is None:
            exclusions.append(
                ExclusionReason(
                    code="IC_PUT_LEG_INVALID",
                    message=f"Iron condor: no valid bull put spread for {stock.symbol} {expiry}",
                    data={"symbol": stock.symbol, "expiry": expiry.isoformat()},
                )
            )
            continue

        # Build bear call spread: short call (lower strike), long call (higher strike). Same width.
        call_short_opt: Optional[NormalizedOptionQuote] = None
        call_long_opt: Optional[NormalizedOptionQuote] = None
        best_call_credit: Optional[float] = None

        for width in IC_SPREAD_WIDTHS:
            for short_call in calls_above:
                short_strike = float(short_call.strike)
                long_strike = short_strike + width
                long_call = next((c for c in calls_above if float(c.strike) == long_strike), None)
                if long_call is None:
                    continue
                mid_short = mid(short_call.bid, short_call.ask)
                mid_long = mid(long_call.bid, long_call.ask)
                if mid_short is None or mid_long is None:
                    continue
                credit_call = (mid_short - mid_long) * 100
                if credit_call <= 0:
                    continue
                if best_call_credit is None or credit_call > best_call_credit:
                    best_call_credit = credit_call
                    call_short_opt = short_call
                    call_long_opt = long_call

        if call_short_opt is None or call_long_opt is None:
            exclusions.append(
                ExclusionReason(
                    code="IC_CALL_LEG_INVALID",
                    message=f"Iron condor: no valid bear call spread for {stock.symbol} {expiry}",
                    data={"symbol": stock.symbol, "expiry": expiry.isoformat()},
                )
            )
            continue

        # One IC per expiry: use the put and call legs we found
        put_short_strike = float(put_short_opt.strike)
        put_long_strike = float(put_long_opt.strike)
        call_short_strike = float(call_short_opt.strike)
        call_long_strike = float(call_long_opt.strike)

        credit_put_val = (mid(put_short_opt.bid, put_short_opt.ask) or 0) - (mid(put_long_opt.bid, put_long_opt.ask) or 0)
        credit_put_val *= 100
        credit_call_val = (mid(call_short_opt.bid, call_short_opt.ask) or 0) - (mid(call_long_opt.bid, call_long_opt.ask) or 0)
        credit_call_val *= 100

        width_put = put_short_strike - put_long_strike
        width_call = call_long_strike - call_short_strike
        max_loss_put = width_put * 100 - credit_put_val
        max_loss_call = width_call * 100 - credit_call_val

        if credit_put_val <= 0 or credit_call_val <= 0:
            exclusions.append(
                ExclusionReason(
                    code="IC_NEGATIVE_CREDIT",
                    message=f"Iron condor: negative credit on put or call leg for {stock.symbol} {expiry}",
                    data={"symbol": stock.symbol, "expiry": expiry.isoformat()},
                )
            )
            continue

        ic = IronCondorCandidate(
            symbol=stock.symbol,
            expiry=expiry,
            put_short_strike=put_short_strike,
            put_long_strike=put_long_strike,
            call_short_strike=call_short_strike,
            call_long_strike=call_long_strike,
            credit_put=credit_put_val,
            credit_call=credit_call_val,
            max_loss_put=max_loss_put,
            max_loss_call=max_loss_call,
            underlying_price=underlying_price,
            option_context=option_context,
        )
        candidates.append(ic)
        # One IC per expiry
        break

    return candidates, exclusions


__all__ = ["IronCondorCandidate", "generate_iron_condor_candidates", "IC_SPREAD_WIDTHS"]
