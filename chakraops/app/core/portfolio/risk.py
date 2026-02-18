# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Risk evaluation helpers — utilization, symbol/sector exposure limits.
   Phase 14.0: Account-based portfolio risk evaluation (max_symbol_collateral, max_deployed_pct, max_near_expiry)."""

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


def _capital_for_position(position: Any) -> float:
    """CSP: strike*100*contracts; CC/STOCK: 0."""
    strat = (getattr(position, "strategy", "") or "").strip().upper()
    if strat == "CSP":
        strike = getattr(position, "strike", None)
        contracts = int(getattr(position, "contracts", 0) or 0)
        if strike is not None and strike > 0 and contracts > 0:
            return float(strike) * 100 * contracts
    return 0.0


def _dte_for_position(position: Any) -> Optional[int]:
    """DTE from expiration. Uses lifecycle compute_dte if available."""
    try:
        from app.core.positions.lifecycle import compute_dte
        exp = getattr(position, "expiration", None) or getattr(position, "expiry", None)
        return compute_dte(exp)
    except Exception:
        return None


def evaluate_portfolio_risk(
    account: Any,
    positions_open: List[Any],
) -> Dict[str, Any]:
    """
    Phase 14.0: Evaluate portfolio risk against account limits.
    Returns {status: PASS|WARN|FAIL, metrics: {...}, breaches: [...]}.
    Breach: {type, subtype, current, limit, message, affected_symbols}.
    Excludes DIAG_TEST positions.
    """
    breaches: List[Dict[str, Any]] = []
    total_capital = float(getattr(account, "total_capital", 0) or 0)
    buying_power = total_capital
    _exclude_diag = lambda p: (getattr(p, "symbol", "") or "").strip().upper().startswith("DIAG_TEST")
    open_pos = [p for p in positions_open if not _exclude_diag(p)]

    capital_deployed = sum(_capital_for_position(p) for p in open_pos)
    buying_power = max(0.0, total_capital - capital_deployed)
    deployed_pct = capital_deployed / total_capital if total_capital > 0 else 0.0

    exposure_by_symbol: Dict[str, float] = {}
    for p in open_pos:
        sym = (getattr(p, "symbol", "") or "").strip().upper()
        if sym:
            exposure_by_symbol[sym] = exposure_by_symbol.get(sym, 0) + _capital_for_position(p)

    top_symbol = max(exposure_by_symbol.items(), key=lambda x: x[1]) if exposure_by_symbol else ("—", 0.0)
    top_symbol_name, top_symbol_collateral = top_symbol

    near_expiry_count = 0
    for p in open_pos:
        dte = _dte_for_position(p)
        if dte is not None and dte <= 7:
            near_expiry_count += 1

    # Check max_symbol_collateral
    max_sym = getattr(account, "max_symbol_collateral", None)
    if max_sym is not None and max_sym > 0:
        for sym, cap in exposure_by_symbol.items():
            if cap > max_sym:
                breaches.append({
                    "type": "PORTFOLIO_RISK",
                    "subtype": "RISK_LIMIT_BREACH",
                    "current": cap,
                    "limit": max_sym,
                    "message": f"Symbol {sym} collateral ${cap:.2f} exceeds max ${max_sym:.2f}",
                    "affected_symbols": [sym],
                })

    # Check max_deployed_pct (cap % of buying power deployed; buying power = total - deployed)
    # Spec says "cap % of buying power deployed" - so deployed / (total) is the deployed fraction.
    max_dep = getattr(account, "max_deployed_pct", None)
    if max_dep is not None and max_dep > 0 and total_capital > 0:
        if deployed_pct > max_dep:
            breaches.append({
                "type": "PORTFOLIO_RISK",
                "subtype": "RISK_LIMIT_BREACH",
                "current": round(deployed_pct, 4),
                "limit": max_dep,
                "message": f"Deployed {deployed_pct:.1%} exceeds max {max_dep:.1%} of capital",
                "affected_symbols": [],
            })

    # Check max_near_expiry_positions
    max_near = getattr(account, "max_near_expiry_positions", None)
    if max_near is not None and max_near >= 0:
        if near_expiry_count > max_near:
            symbols_near = []
            for p in open_pos:
                dte = _dte_for_position(p)
                if dte is not None and dte <= 7:
                    symbols_near.append((getattr(p, "symbol", "") or "").strip().upper())
            breaches.append({
                "type": "PORTFOLIO_RISK",
                "subtype": "RISK_LIMIT_BREACH",
                "current": near_expiry_count,
                "limit": max_near,
                "message": f"Near-expiry (DTE<=7) positions {near_expiry_count} exceeds max {max_near}",
                "affected_symbols": list(dict.fromkeys(symbols_near)),
            })

    fail_count = sum(1 for b in breaches if b.get("subtype") == "RISK_LIMIT_BREACH")
    if fail_count > 0:
        status = "FAIL"
    elif breaches:
        status = "WARN"
    else:
        status = "PASS"

    metrics = {
        "capital_deployed": round(capital_deployed, 2),
        "total_capital": round(total_capital, 2),
        "buying_power": round(buying_power, 2),
        "deployed_pct": round(deployed_pct, 4),
        "top_symbol": top_symbol_name,
        "top_symbol_collateral": round(top_symbol_collateral, 2),
        "near_expiry_count": near_expiry_count,
        "open_positions_count": len(open_pos),
    }
    return {"status": status, "metrics": metrics, "breaches": breaches}
