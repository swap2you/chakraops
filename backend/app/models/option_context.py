# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""OptionContext: volatility and probability metrics for symbol/expiry gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OptionContext:
    """Rich volatility and probability metrics for a symbol (and optionally expiry).

    Used to gate or weight strategy selection. All numeric metrics are optional;
    missing data is represented as None.
    """

    symbol: str
    """Ticker symbol (e.g., AAPL)."""

    expected_move_1sd: Optional[float] = None
    """Expected one-standard-deviation move (decimal, e.g., 0.05 = 5%). From ATM straddle or ORATS impliedMove."""

    iv_rank: Optional[float] = None
    """IV rank: where current IV sits in 1y range (0–100). From ORATS ivrank or computed from history."""

    iv_percentile: Optional[float] = None
    """IV percentile (0–100). From ORATS ivPct1y or computed."""

    term_structure_slope: Optional[float] = None
    """Near-term IV minus longer-term IV (e.g., iv30d - iv90d). Positive = backwardation, negative = contango."""

    skew_metric: Optional[float] = None
    """Put-call IV skew: 25-delta call IV minus 25-delta put IV. From ORATS skewing or computed."""

    days_to_earnings: Optional[int] = None
    """Days to next earnings. None if unknown or no upcoming earnings."""

    event_flags: List[str] = field(default_factory=list)
    """Major macro event flags: e.g. FOMC, CPI, NFP when within a configured window."""

    raw: Dict[str, Any] = field(default_factory=dict)
    """Optional raw payload from provider for debugging."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging/snapshots."""
        return {
            "symbol": self.symbol,
            "expected_move_1sd": self.expected_move_1sd,
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "term_structure_slope": self.term_structure_slope,
            "skew_metric": self.skew_metric,
            "days_to_earnings": self.days_to_earnings,
            "event_flags": list(self.event_flags),
            "raw_keys": list(self.raw.keys()) if self.raw else [],
        }


def option_context_from_dict(data: Dict[str, Any]) -> OptionContext:
    """Build OptionContext from a dict (e.g., from JSON)."""
    return OptionContext(
        symbol=str(data.get("symbol", "")),
        expected_move_1sd=data.get("expected_move_1sd"),
        iv_rank=data.get("iv_rank"),
        iv_percentile=data.get("iv_percentile"),
        term_structure_slope=data.get("term_structure_slope"),
        skew_metric=data.get("skew_metric"),
        days_to_earnings=data.get("days_to_earnings"),
        event_flags=list(data.get("event_flags") or []),
        raw=data.get("raw") or {},
    )
