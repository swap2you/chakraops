# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Risk evaluation helpers — utilization, symbol/sector exposure limits."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.portfolio.models import RiskFlag, RiskProfile
from app.core.market.company_data import get_sector


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def evaluate_risk_flags(
    total_equity: float,
    capital_in_use: float,
    available_capital: float,
    open_positions_count: int,
    exposure_by_symbol: Dict[str, float],
    exposure_by_sector: Dict[str, float],
    profile: RiskProfile,
    positions_by_sector: Dict[str, int],
) -> List[RiskFlag]:
    """Compute risk flags against profile thresholds."""
    flags: List[RiskFlag] = []
    if total_equity <= 0:
        return flags

    util_pct = capital_in_use / total_equity if total_equity > 0 else 0.0
    max_util = profile.max_capital_utilization_pct
    if max_util > 0 and util_pct > max_util:
        flags.append(RiskFlag(
            code="OVER_UTILIZATION",
            message=f"Capital utilization {util_pct:.1%} exceeds max {max_util:.1%}",
            severity="error",
            meta={"utilization_pct": util_pct, "max_pct": max_util},
        ))

    # Single symbol exposure
    max_sym = profile.max_single_symbol_exposure_pct
    if max_sym > 0:
        for sym, cap in exposure_by_symbol.items():
            if cap > 0 and total_equity > 0:
                pct = cap / total_equity
                if pct > max_sym:
                    flags.append(RiskFlag(
                        code="OVER_SYMBOL_EXPOSURE",
                        message=f"Would exceed max single symbol exposure ({sym} {pct:.1%} > {max_sym:.1%})",
                        severity="error",
                        meta={"symbol": sym, "pct": pct, "max_pct": max_sym},
                    ))

    # Sector exposure
    max_sec = profile.max_single_sector_exposure_pct
    if max_sec > 0:
        for sector, cap in exposure_by_sector.items():
            if cap > 0 and total_equity > 0:
                pct = cap / total_equity
                if pct > max_sec:
                    flags.append(RiskFlag(
                        code="OVER_SECTOR_EXPOSURE",
                        message=f"Would exceed max sector exposure ({sector} {pct:.1%} > {max_sec:.1%})",
                        severity="error",
                        meta={"sector": sector, "pct": pct, "max_pct": max_sec},
                    ))

    # Too many positions
    if profile.max_open_positions > 0 and open_positions_count > profile.max_open_positions:
        flags.append(RiskFlag(
            code="TOO_MANY_POSITIONS",
            message=f"Open positions {open_positions_count} exceeds max {profile.max_open_positions}",
            severity="error",
            meta={"count": open_positions_count, "max": profile.max_open_positions},
        ))

    # Too many per sector
    max_per_sector = profile.max_positions_per_sector
    if max_per_sector > 0:
        for sector, count in positions_by_sector.items():
            if count > max_per_sector:
                flags.append(RiskFlag(
                    code="TOO_MANY_PER_SECTOR",
                    message=f"Sector {sector} has {count} positions, max {max_per_sector}",
                    severity="error",
                    meta={"sector": sector, "count": count, "max": max_per_sector},
                ))

    return flags


def would_exceed_limits(
    profile: RiskProfile,
    total_equity: float,
    capital_in_use: float,
    open_positions_count: int,
    exposure_by_symbol: Dict[str, float],
    exposure_by_sector: Dict[str, float],
    positions_by_sector: Dict[str, int],
    candidate_symbol: str,
    candidate_capital: float,
    candidate_sector: str,
) -> Tuple[bool, List[str]]:
    """
    Check if adding a candidate would exceed limits.
    Returns (would_exceed, list of human-readable reasons).
    """
    reasons: List[str] = []
    if total_equity <= 0:
        return False, reasons

    # Simulate adding candidate
    new_capital_in_use = capital_in_use + candidate_capital
    new_util = new_capital_in_use / total_equity
    if profile.max_capital_utilization_pct > 0 and new_util > profile.max_capital_utilization_pct:
        reasons.append(
            f"Would exceed max capital utilization ({new_util:.1%} > {profile.max_capital_utilization_pct:.1%})"
        )

    # Symbol exposure
    sym_cap = exposure_by_symbol.get(candidate_symbol, 0) + candidate_capital
    sym_pct = sym_cap / total_equity if total_equity > 0 else 0
    if profile.max_single_symbol_exposure_pct > 0 and sym_pct > profile.max_single_symbol_exposure_pct:
        reasons.append(
            f"Would exceed max single symbol exposure ({candidate_symbol} {sym_pct:.1%} > {profile.max_single_symbol_exposure_pct:.1%})"
        )

    # Sector exposure
    sec_cap = exposure_by_sector.get(candidate_sector, 0) + candidate_capital
    sec_pct = sec_cap / total_equity if total_equity > 0 else 0
    if profile.max_single_sector_exposure_pct > 0 and sec_pct > profile.max_single_sector_exposure_pct:
        reasons.append(
            f"Would exceed max sector exposure ({candidate_sector} {sec_pct:.1%} > {profile.max_single_sector_exposure_pct:.1%})"
        )

    # Position count
    if profile.max_open_positions > 0 and open_positions_count >= profile.max_open_positions:
        reasons.append(
            f"Max open positions reached ({open_positions_count} >= {profile.max_open_positions})"
        )

    # Positions per sector
    sec_count = positions_by_sector.get(candidate_sector, 0) + 1
    if profile.max_positions_per_sector > 0 and sec_count > profile.max_positions_per_sector:
        reasons.append(
            f"Would exceed max positions in sector {candidate_sector} ({sec_count} > {profile.max_positions_per_sector})"
        )

    return len(reasons) > 0, reasons
