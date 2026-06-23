# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Portfolio-aware position sizing with hard risk invariants (R33.0).

Sizing respects the cash buffer, per-position allocation, and symbol/sector
exposure caps. Mandatory invariants are enforced structurally:

- no uncovered covered call (CC contracts * 100 <= shares held)
- no CSP requiring more reserved cash than available (after buffer)
- no negative or impossible quantity
- cash buffer is preserved
- no automatic order creation (advisory only)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.decision_engine.contract import (
    COVERED_CALL,
    CSP,
    DecisionInput,
    PortfolioState,
    SHARE_BUY,
    Sizing,
)
from app.core.decision_engine.profiles import StrategyProfile


@dataclass(frozen=True)
class SizingResult:
    sizing: Sizing
    capital_required: float
    risk_flags: List[str] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return (self.sizing.contracts > 0) or (self.sizing.shares > 0)


def _buffer_and_caps(profile: StrategyProfile, portfolio: PortfolioState, symbol: str, sector: Optional[str]) -> Tuple[float, float, float, Optional[float], List[str]]:
    flags: List[str] = []
    cash_buffer_amount = portfolio.total_value * profile.cash_buffer_pct / 100.0
    available_after_buffer = max(0.0, portfolio.available_cash - cash_buffer_amount)
    max_position_dollars = portfolio.total_value * profile.max_position_allocation_pct / 100.0

    max_symbol_dollars = portfolio.total_value * profile.max_symbol_exposure_pct / 100.0
    existing_symbol = float(portfolio.symbol_exposure.get(symbol, 0.0))
    symbol_headroom = max(0.0, max_symbol_dollars - existing_symbol)

    sector_headroom: Optional[float] = None
    if sector and str(sector).upper() != "UNKNOWN":
        # Sector known: always enforce the cap against existing exposure (0 when
        # the portfolio has no position in that sector yet).
        max_sector_dollars = portfolio.total_value * profile.max_sector_exposure_pct / 100.0
        existing_sector = float(portfolio.sector_exposure.get(sector, 0.0))
        sector_headroom = max(0.0, max_sector_dollars - existing_sector)
        flags.append("SECTOR_CAP_ENFORCED")
    else:
        # Sector unavailable. For incremental cash-consuming strategies the
        # engine's sector_gate has already blocked; the flag documents the cause.
        flags.append("SECTOR_DATA_UNAVAILABLE")

    return available_after_buffer, max_position_dollars, symbol_headroom, sector_headroom, flags


def _dollar_budget(available_after_buffer: float, max_position_dollars: float, symbol_headroom: float, sector_headroom: Optional[float]) -> float:
    budget = min(available_after_buffer, max_position_dollars, symbol_headroom)
    if sector_headroom is not None:
        budget = min(budget, sector_headroom)
    return max(0.0, budget)


def size_csp(inp: DecisionInput, profile: StrategyProfile, portfolio: PortfolioState) -> SizingResult:
    c = inp.contract
    if c is None or not c.strike:
        return SizingResult(Sizing(explanation=["No contract to size"]), 0.0, ["MISSING_CONTRACT"])
    collateral_per = c.strike * 100.0
    available_after_buffer, max_pos, sym_head, sec_head, flags = _buffer_and_caps(profile, portfolio, inp.symbol, inp.sector)
    budget = _dollar_budget(available_after_buffer, max_pos, sym_head, sec_head)
    contracts = int(math.floor(budget / collateral_per)) if collateral_per > 0 else 0
    contracts = max(0, contracts)
    reserved = contracts * collateral_per

    # Invariants (defensive; construction already guarantees these).
    if reserved > available_after_buffer + 1e-6:
        contracts = int(math.floor(available_after_buffer / collateral_per))
        contracts = max(0, contracts)
        reserved = contracts * collateral_per
    assert reserved <= portfolio.available_cash + 1e-6, "CSP reserved cash exceeds available cash"
    assert contracts >= 0, "CSP contracts negative"

    explanation = [
        f"available_after_buffer=${available_after_buffer:,.2f}",
        f"max_position=${max_pos:,.2f}",
        f"symbol_headroom=${sym_head:,.2f}",
        f"collateral_per_contract=${collateral_per:,.2f}",
        f"contracts={contracts} reserved_cash=${reserved:,.2f}",
    ]
    if contracts == 0:
        flags.append("CASH_INSUFFICIENT_FOR_ONE_CONTRACT")
    return SizingResult(Sizing(contracts=contracts, explanation=explanation), reserved, flags)


def size_covered_call(inp: DecisionInput, profile: StrategyProfile, portfolio: PortfolioState) -> SizingResult:
    shares = int(inp.shares_held or 0)
    contracts_by_shares = shares // 100
    contracts = max(0, contracts_by_shares)

    # Invariant: never write more contracts than fully-covered lots.
    assert contracts * 100 <= shares, "uncovered covered call"
    assert contracts >= 0, "CC contracts negative"

    explanation = [
        f"shares_held={shares}",
        f"fully_covered_lots={contracts_by_shares}",
        f"contracts={contracts} capital_required=$0.00 (shares already held)",
    ]
    flags: List[str] = []
    # Covered calls write against shares already owned, so they add no incremental
    # sector exposure and may proceed even when sector data is unavailable — but
    # we surface the data gap explicitly rather than silently.
    if not (inp.sector and str(inp.sector).upper() != "UNKNOWN"):
        flags.append("SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION")
    if contracts == 0:
        flags.append("INSUFFICIENT_SHARES_FOR_ONE_LOT")
    return SizingResult(Sizing(contracts=contracts, explanation=explanation), 0.0, flags)


def size_share_buy(inp: DecisionInput, profile: StrategyProfile, portfolio: PortfolioState) -> SizingResult:
    if inp.price is None or inp.price <= 0:
        return SizingResult(Sizing(explanation=["No price to size"]), 0.0, ["MISSING_PRICE"])
    available_after_buffer, max_pos, sym_head, sec_head, flags = _buffer_and_caps(profile, portfolio, inp.symbol, inp.sector)
    budget = _dollar_budget(available_after_buffer, max_pos, sym_head, sec_head)
    shares = int(math.floor(budget / inp.price))
    shares = max(0, shares)
    capital = shares * inp.price

    if capital > available_after_buffer + 1e-6:
        shares = int(math.floor(available_after_buffer / inp.price))
        shares = max(0, shares)
        capital = shares * inp.price
    assert capital <= portfolio.available_cash + 1e-6, "share-buy capital exceeds available cash"
    assert shares >= 0, "share-buy shares negative"

    explanation = [
        f"available_after_buffer=${available_after_buffer:,.2f}",
        f"max_position=${max_pos:,.2f}",
        f"symbol_headroom=${sym_head:,.2f}",
        f"price=${inp.price:,.2f}",
        f"shares={shares} capital_required=${capital:,.2f}",
    ]
    if shares == 0:
        flags.append("CASH_INSUFFICIENT_FOR_SHARES")
    return SizingResult(Sizing(shares=shares, explanation=explanation), capital, flags)


def size_position(inp: DecisionInput, profile: StrategyProfile, portfolio: PortfolioState) -> SizingResult:
    if inp.strategy == CSP:
        return size_csp(inp, profile, portfolio)
    if inp.strategy == COVERED_CALL:
        return size_covered_call(inp, profile, portfolio)
    if inp.strategy == SHARE_BUY:
        return size_share_buy(inp, profile, portfolio)
    return SizingResult(Sizing(explanation=[f"Unknown strategy {inp.strategy}"]), 0.0, ["UNKNOWN_STRATEGY"])
