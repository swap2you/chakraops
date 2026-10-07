# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Signal models: immutable dataclasses for CSP/CC candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.models.option_context import OptionContext


class SignalType(str, Enum):
    """Signal type enumeration."""

    CSP = "CSP"
    CC = "CC"


@dataclass(frozen=True)
class ExplanationItem:
    """Explanation item for why a signal was generated or scored."""

    code: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExclusionReason:
    """Reason why a symbol/contract was excluded from signal generation."""

    code: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExclusionDetail:
    """Detailed exclusion information for DecisionSnapshot (Phase 7.2).
    
    Provides structured exclusion details with symbol, rule, message, stage,
    and optional metadata for display in dashboard and alerts.
    """

    symbol: str
    rule: str  # Exclusion code/rule identifier
    message: str
    stage: str  # e.g., "CHAIN_FETCH", "CSP_GENERATION", "CC_GENERATION", "NORMALIZATION"
    metadata: Dict[str, Any] | None = None


@dataclass(frozen=True)
class SignalCandidate:
    """Immutable signal candidate (CSP or CC)."""

    symbol: str
    signal_type: SignalType
    as_of: datetime
    underlying_price: float
    expiry: date
    strike: float
    option_right: str  # "PUT" or "CALL"
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    delta: Optional[float] = None
    prob_otm: Optional[float] = None  # Probability OTM (0–1), from ORATS when available
    iv_rank: Optional[float] = None   # IV rank (e.g. 0–100), from ORATS when available
    iv: Optional[float] = None
    annualized_yield: Optional[float] = None
    raw_yield: Optional[float] = None
    max_profit: Optional[float] = None
    collateral: Optional[float] = None
    explanation: List[ExplanationItem] = field(default_factory=list)
    exclusions: List[ExclusionReason] = field(default_factory=list)
    # Phase 3.2: volatility/probability context for gating and weighting
    option_context: Optional["OptionContext"] = None

    def __post_init__(self) -> None:
        """Validate option_right."""
        if self.option_right not in ("PUT", "CALL"):
            raise ValueError(f"option_right must be PUT or CALL, got {self.option_right}")
        if self.signal_type == SignalType.CSP and self.option_right != "PUT":
            raise ValueError(f"CSP signals must use PUT options, got {self.option_right}")
        if self.signal_type == SignalType.CC and self.option_right != "CALL":
            raise ValueError(f"CC signals must use CALL options, got {self.option_right}")


@dataclass(frozen=True)
class SignalEngineConfig:
    """Base configuration for signal engine (common to CSP and CC).

    Parameters
    ----------
    dte_min:
        Minimum days-to-expiration (inclusive) for contracts to consider.
    dte_max:
        Maximum days-to-expiration (inclusive) for contracts to consider.
    min_bid:
        Minimum bid price for options to be considered.
    min_open_interest:
        Minimum open interest for options to be considered.
    max_spread_pct:
        Maximum allowed bid/ask spread percentage.
    max_expiries_per_symbol:
        Hard cap on the number of expirations processed per symbol (to bound
        runtime when providers return very long expiry lists).
    """

    dte_min: int
    dte_max: int
    min_bid: float
    min_open_interest: int
    max_spread_pct: float
    max_expiries_per_symbol: int = 12
    # Optional scoring configuration (Phase 4A). When None, scoring is disabled
    # and the engine behaves as in Phase 3.
    scoring_config: "ScoringConfig | None" = None
    # Optional selection configuration (Phase 4A Step 2). When None, selection
    # is skipped even if scoring is enabled.
    selection_config: "SelectionConfig | None" = None


@dataclass(frozen=True)
class CSPConfig:
    """Configuration specific to Cash-Secured Put signals. Uses delta and prob_otm (no OTM%)."""

    delta_min: float  # Absolute put delta min (e.g. 0.15 -> -0.25)
    delta_max: float  # Absolute put delta max (e.g. 0.25 -> -0.15)
    prob_otm_min: float = 0.70  # Minimum probability OTM (e.g. 0.70 for 70%)


@dataclass(frozen=True)
class CCConfig:
    """Configuration specific to Covered Call signals. Uses delta and prob_otm (no OTM%)."""

    delta_min: float  # Call delta min (e.g. 0.15)
    delta_max: float  # Call delta max (e.g. 0.35)
    prob_otm_min: float = 0.70  # Minimum probability OTM (e.g. 0.70 for 70%)


__all__ = [
    "SignalType",
    "SignalCandidate",
    "ExplanationItem",
    "ExclusionReason",
    "ExclusionDetail",
    "SignalEngineConfig",
    "CSPConfig",
    "CCConfig",
]
