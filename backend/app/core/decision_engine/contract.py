# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical decision input/output contract (R33.0).

One contract for the advisory decision engine. Inputs describe a candidate
(symbol + already-fetched, freshness-stamped data + portfolio context); outputs
describe a single advisory, manual-only recommendation with full provenance:
status, eligibility, sizing, capital, expected return, risk flags, score, rank,
and reason codes.

These are plain dataclasses (no I/O) so they are deterministic and trivially
serializable for the API and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Market regimes (mirror profiles.KNOWN_REGIMES).
BULL = "BULL"
NEUTRAL = "NEUTRAL"
BEAR = "BEAR"
VOLATILE = "VOLATILE"

# Strategy types.
CSP = "CSP"
COVERED_CALL = "COVERED_CALL"
SHARE_BUY = "SHARE_BUY"
CASH = "CASH"

STRATEGY_TYPES = (CSP, COVERED_CALL, SHARE_BUY)

# Decision statuses.
ACTIONABLE = "ACTIONABLE"
WATCH = "WATCH"
BLOCKED = "BLOCKED"
STAY_IN_CASH = "STAY_IN_CASH"

# Data-quality labels.
DQ_OK = "OK"
DQ_DEGRADED = "DEGRADED"
DQ_BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class OptionContract:
    """Candidate option contract (already selected upstream)."""

    delta: float
    dte: int
    premium: float  # per-share option premium (dollars)
    strike: float
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    bid_ask_spread_pct: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "delta": self.delta,
            "dte": self.dte,
            "premium": self.premium,
            "strike": self.strike,
            "open_interest": self.open_interest,
            "volume": self.volume,
            "bid_ask_spread_pct": self.bid_ask_spread_pct,
        }


@dataclass(frozen=True)
class PortfolioState:
    """Portfolio context used for sizing and exposure caps."""

    total_value: float
    available_cash: float
    symbol_exposure: Dict[str, float] = field(default_factory=dict)  # symbol -> $ exposure
    sector_exposure: Dict[str, float] = field(default_factory=dict)  # sector -> $ exposure

    def to_dict(self) -> dict:
        return {
            "total_value": self.total_value,
            "available_cash": self.available_cash,
            "symbol_exposure": dict(self.symbol_exposure),
            "sector_exposure": dict(self.sector_exposure),
        }


@dataclass(frozen=True)
class DecisionInput:
    """Canonical input for one (symbol, strategy) candidate.

    Timestamps (``*_as_of``) are ISO strings or None; None means missing data.
    ``market_regime`` is one of the regime constants. ``earnings_days`` is the
    number of calendar days until the next earnings event (None == unknown).
    """

    symbol: str
    strategy: str
    market_regime: str
    price: Optional[float] = None
    iv_rank: Optional[float] = None
    price_as_of: Optional[str] = None
    chain_as_of: Optional[str] = None
    earnings_days: Optional[int] = None
    contract: Optional[OptionContract] = None
    shares_held: int = 0
    sector: Optional[str] = None
    # Honest upstream liquidity gate (batch Stage-2); do not invent fake OI/volume.
    liquidity_validated_upstream: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "market_regime": self.market_regime,
            "price": self.price,
            "iv_rank": self.iv_rank,
            "price_as_of": self.price_as_of,
            "chain_as_of": self.chain_as_of,
            "earnings_days": self.earnings_days,
            "contract": self.contract.to_dict() if self.contract else None,
            "shares_held": self.shares_held,
            "sector": self.sector,
            "liquidity_validated_upstream": self.liquidity_validated_upstream,
        }


@dataclass(frozen=True)
class Sizing:
    """Sizing result for a recommendation."""

    contracts: int = 0
    shares: int = 0
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "contracts": self.contracts,
            "shares": self.shares,
            "explanation": list(self.explanation),
        }


@dataclass(frozen=True)
class DecisionOutput:
    """Canonical advisory output for one candidate. Manual-only."""

    symbol: str
    strategy: str
    profile: str
    market_regime: str
    decision_status: str
    eligibility: bool
    data_quality: str
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    event_risk: Dict[str, Any] = field(default_factory=dict)
    selected_contract: Optional[Dict[str, Any]] = None
    sizing: Dict[str, Any] = field(default_factory=dict)
    capital_required: float = 0.0
    expected_return_pct: Optional[float] = None
    expected_return_dollars: Optional[float] = None
    risk_flags: List[str] = field(default_factory=list)
    score: float = 0.0
    rank: Optional[int] = None
    reason_codes: List[str] = field(default_factory=list)
    manual_only: bool = True

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "profile": self.profile,
            "market_regime": self.market_regime,
            "decision_status": self.decision_status,
            "eligibility": self.eligibility,
            "data_quality": self.data_quality,
            "data_freshness": dict(self.data_freshness),
            "event_risk": dict(self.event_risk),
            "selected_contract": self.selected_contract,
            "sizing": dict(self.sizing),
            "capital_required": self.capital_required,
            "expected_return_pct": self.expected_return_pct,
            "expected_return_dollars": self.expected_return_dollars,
            "risk_flags": list(self.risk_flags),
            "score": self.score,
            "rank": self.rank,
            "reason_codes": list(self.reason_codes),
            "manual_only": self.manual_only,
        }
