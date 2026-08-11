# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Eligibility and safety gates for the decision engine (R33.0).

Gates decide whether a candidate may produce an actionable recommendation.
Data-safety gates wire the R32 ``stale_data_gate`` so missing or stale critical
data blocks action. Gates return ``(passed, reason_codes)`` and never fall back
to an alternate data source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.core.data_reliability.freshness import (
    FreshnessResult,
    evaluate_freshness,
    stale_data_gate,
)
from app.core.decision_engine.contract import (
    COVERED_CALL,
    CSP,
    DecisionInput,
    SHARE_BUY,
)
from app.core.decision_engine.profiles import StrategyProfile

# Default freshness budgets (seconds). ChakraOps uses delayed/EOD data, so a
# one-trading-day budget is the default; callers may override.
DEFAULT_PRICE_MAX_AGE_SECONDS = 24 * 3600
DEFAULT_CHAIN_MAX_AGE_SECONDS = 24 * 3600


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def check_data_freshness(
    inp: DecisionInput,
    *,
    now: Optional[datetime] = None,
    price_max_age_seconds: float = DEFAULT_PRICE_MAX_AGE_SECONDS,
    chain_max_age_seconds: float = DEFAULT_CHAIN_MAX_AGE_SECONDS,
):
    """Return the R32 stale-data gate result for this candidate's inputs.

    PRICE is always required. OPTIONS_CHAIN is required for option strategies
    (CSP / covered call) and optional for share-buy.
    """
    now = now or datetime.now(timezone.utc)
    results: List[FreshnessResult] = [
        evaluate_freshness(
            "PRICE",
            _parse_iso(inp.price_as_of),
            max_age_seconds=price_max_age_seconds,
            now=now,
            required=True,
        )
    ]
    chain_required = inp.strategy in (CSP, COVERED_CALL)
    results.append(
        evaluate_freshness(
            "OPTIONS_CHAIN",
            _parse_iso(inp.chain_as_of),
            max_age_seconds=chain_max_age_seconds,
            now=now,
            required=chain_required,
        )
    )
    return stale_data_gate(results)


def check_missing_critical(inp: DecisionInput) -> Tuple[bool, List[str]]:
    """Block when critical fields needed to act are absent."""
    reasons: List[str] = []
    if inp.price is None:
        reasons.append("MISSING_PRICE")
    if inp.strategy in (CSP, COVERED_CALL):
        c = inp.contract
        if c is None:
            reasons.append("MISSING_CONTRACT")
        else:
            if c.strike is None or c.strike <= 0:
                reasons.append("MISSING_STRIKE")
            if c.premium is None or c.premium < 0:
                reasons.append("MISSING_PREMIUM")
            if c.delta is None:
                reasons.append("MISSING_DELTA")
            if c.dte is None:
                reasons.append("MISSING_DTE")
    return (not reasons, reasons)


def regime_gate(inp: DecisionInput, profile: StrategyProfile) -> Tuple[bool, List[str]]:
    """Allow only regimes the profile accepts."""
    regime = (inp.market_regime or "").upper()
    if regime not in profile.acceptable_regimes:
        return (False, [f"REGIME_EXCLUDED_{regime or 'UNKNOWN'}"])
    return (True, [])


def earnings_gate(inp: DecisionInput, profile: StrategyProfile) -> Tuple[bool, List[str]]:
    """Block when an earnings event falls inside the profile blackout window.

    Unknown earnings timing (None) does not hard-block, but the caller records
    an EARNINGS_DATA_UNAVAILABLE risk flag (see strategies/engine).
    """
    if profile.earnings_blackout_days <= 0:
        return (True, [])
    if inp.earnings_days is None:
        return (True, [])  # unknown handled as a risk flag, not a hard block
    if inp.earnings_days <= profile.earnings_blackout_days:
        return (False, [f"EARNINGS_BLACKOUT_{inp.earnings_days}D"])
    return (True, [])


def liquidity_gate(inp: DecisionInput, profile: StrategyProfile) -> Tuple[bool, List[str]]:
    """Require contract liquidity to meet the profile minimums (option strategies)."""
    if inp.strategy not in (CSP, COVERED_CALL):
        return (True, [])
    c = inp.contract
    if c is None:
        return (False, ["LIQUIDITY_DATA_MISSING"])
    # Upstream batch Stage-2 already validated liquidity; do not invent OI/volume.
    if getattr(inp, "liquidity_validated_upstream", False):
        return (True, ["LIQUIDITY_VALIDATED_UPSTREAM"])
    reasons: List[str] = []
    req = profile.liquidity
    if c.open_interest is None or c.volume is None or c.bid_ask_spread_pct is None:
        return (False, ["LIQUIDITY_DATA_MISSING"])
    if c.open_interest < req.min_open_interest:
        reasons.append("LOW_OPEN_INTEREST")
    if c.volume < req.min_volume:
        reasons.append("LOW_VOLUME")
    if c.bid_ask_spread_pct > req.max_bid_ask_spread_pct:
        reasons.append("WIDE_SPREAD")
    return (not reasons, reasons)


def holdings_gate(inp: DecisionInput) -> Tuple[bool, List[str]]:
    """Covered calls require >= 100 shares held (no uncovered calls)."""
    if inp.strategy != COVERED_CALL:
        return (True, [])
    if (inp.shares_held or 0) < 100:
        return (False, ["INSUFFICIENT_SHARES"])
    return (True, [])


def sector_gate(inp: DecisionInput, profile: StrategyProfile, portfolio) -> Tuple[bool, List[str]]:
    """Enforce profile sector-exposure caps for incremental cash-consuming exposure.

    Applies to CSP and SHARE_BUY, which add NEW sector exposure. Covered calls on
    already-owned shares are exempt (no incremental sector exposure) — sizing
    flags missing sector data on those separately.

    Safe policy (R34.0): when the symbol's sector cannot be determined, BLOCK the
    incremental exposure rather than silently bypassing the sector cap. When the
    sector is known and already at/over the profile cap, BLOCK as well.
    """
    if inp.strategy not in (CSP, SHARE_BUY):
        return (True, [])
    sector = (inp.sector or "").strip()
    if not sector or sector.upper() == "UNKNOWN":
        return (False, ["SECTOR_DATA_UNAVAILABLE", "SECTOR_BLOCKED_PENDING_DATA"])
    max_sector_dollars = portfolio.total_value * profile.max_sector_exposure_pct / 100.0
    existing = float(portfolio.sector_exposure.get(sector, 0.0))
    if existing >= max_sector_dollars - 1e-6:
        return (False, ["SECTOR_EXPOSURE_LIMIT_REACHED"])
    return (True, [])


def cash_gate(inp: DecisionInput, profile: StrategyProfile, available_cash_after_buffer: float) -> Tuple[bool, List[str]]:
    """CSPs require at least one contract of collateral after the cash buffer."""
    if inp.strategy != CSP:
        return (True, [])
    c = inp.contract
    if c is None or c.strike is None:
        return (False, ["MISSING_CONTRACT"])
    one_contract_collateral = c.strike * 100.0
    if available_cash_after_buffer < one_contract_collateral:
        return (False, ["INSUFFICIENT_CASH"])
    return (True, [])
