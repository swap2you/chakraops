# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Portfolio models — summary, exposure, risk profile, risk flags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RiskProfile:
    """User-configurable risk thresholds. Persisted to out/portfolio/risk_profile.json."""

    max_capital_utilization_pct: float = 0.35
    max_single_symbol_exposure_pct: float = 0.10
    max_single_sector_exposure_pct: float = 0.25
    max_open_positions: int = 12
    max_positions_per_sector: int = 4
    allowlist_symbols: List[str] = field(default_factory=list)
    denylist_symbols: List[str] = field(default_factory=list)
    preferred_strategies: List[str] = field(default_factory=lambda: ["CSP", "CC", "STOCK"])
    stop_loss_cooldown_days: Optional[int] = None  # Do not open new if last stop-loss within X days (default off)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_capital_utilization_pct": self.max_capital_utilization_pct,
            "max_single_symbol_exposure_pct": self.max_single_symbol_exposure_pct,
            "max_single_sector_exposure_pct": self.max_single_sector_exposure_pct,
            "max_open_positions": self.max_open_positions,
            "max_positions_per_sector": self.max_positions_per_sector,
            "allowlist_symbols": self.allowlist_symbols,
            "denylist_symbols": self.denylist_symbols,
            "preferred_strategies": self.preferred_strategies,
            "stop_loss_cooldown_days": self.stop_loss_cooldown_days,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RiskProfile":
        if not d:
            return cls()
        return cls(
            max_capital_utilization_pct=float(d.get("max_capital_utilization_pct", 0.35)),
            max_single_symbol_exposure_pct=float(d.get("max_single_symbol_exposure_pct", 0.10)),
            max_single_sector_exposure_pct=float(d.get("max_single_sector_exposure_pct", 0.25)),
            max_open_positions=int(d.get("max_open_positions", 12)),
            max_positions_per_sector=int(d.get("max_positions_per_sector", 4)),
            allowlist_symbols=list(d.get("allowlist_symbols", [])),
            denylist_symbols=list(d.get("denylist_symbols", [])),
            preferred_strategies=list(d.get("preferred_strategies", ["CSP", "CC", "STOCK"])),
            stop_loss_cooldown_days=d.get("stop_loss_cooldown_days"),
        )


@dataclass
class ExposureItem:
    """Exposure for a symbol or sector."""

    key: str  # symbol or sector name
    required_capital: float
    pct_of_total_equity: float
    pct_of_available_capital: float
    position_count: int = 0
    meta: Optional[Dict[str, Any]] = None


@dataclass
class RiskFlag:
    """Portfolio risk flag."""

    code: str
    message: str
    severity: str  # "error" | "warning"
    meta: Optional[Dict[str, Any]] = None


@dataclass
class PortfolioSummary:
    """Portfolio aggregation from accounts + tracked positions."""

    total_equity: float
    capital_in_use: float
    available_capital: float
    capital_utilization_pct: float
    open_positions_count: int
    risk_flags: List[RiskFlag] = field(default_factory=list)
    available_capital_clamped: bool = False  # True if available was clamped from negative
