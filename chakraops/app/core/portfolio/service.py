# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Portfolio service — compute summary, exposures, risk metrics.

Assumptions (per Phase 3 spec):
- We do not know real broker balances; we rely on user-defined Accounts equity and manual tracked positions.
- Required capital for CSP = collateral = strike * 100 * contracts.
- For CC, required capital is 0 (shares already owned). Still count exposure by symbol optionally (Phase 3: 0).
- Sector mapping is local; unknown sectors treated conservatively (bucketed as "Unknown").
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.portfolio.models import ExposureItem, PortfolioSummary, RiskFlag, RiskProfile
from app.core.portfolio.store import load_risk_profile
from app.core.portfolio.risk import evaluate_risk_flags
from app.core.market.company_data import get_sector

logger = logging.getLogger(__name__)


def _capital_for_position(position: Any) -> float:
    """
    Compute required capital for a position.
    CSP: strike * 100 * contracts
    CC: 0 (shares already owned)
    STOCK: 0 for Phase 3 (or optionally quantity * price if we had price)
    """
    strat = (position.strategy or "").strip().upper()
    if strat == "CSP":
        strike = getattr(position, "strike", None)
        contracts = int(getattr(position, "contracts", 0) or 0)
        if strike is not None and strike > 0 and contracts > 0:
            return float(strike) * 100 * contracts
    elif strat == "CC":
        # CC: 0 — shares already owned
        return 0.0
    elif strat == "STOCK":
        # Phase 3: keep 0 for STOCK exposure capital (no price in position)
        return 0.0
    return 0.0


def compute_portfolio_summary(
    accounts: List[Any],
    positions: List[Any],
    risk_profile: Optional[RiskProfile] = None,
) -> PortfolioSummary:
    """
    Compute portfolio aggregation from accounts + tracked positions.

    - total_equity = sum of account total_capital (active only)
    - capital_in_use = sum of required capital for OPEN/PARTIAL_EXIT positions
    - available_capital = total_equity - capital_in_use (clamped at 0)
    - capital_utilization_pct
    """
    total_equity = 0.0
    for a in accounts:
        if getattr(a, "active", True):
            total_equity += float(getattr(a, "total_capital", 0) or 0)

    # Phase 8.6: Exclude DIAG_TEST positions (diagnostics sanity check) from portfolio totals
    _exclude_diag = lambda p: (getattr(p, "symbol", "") or "").strip().upper().startswith("DIAG_TEST")
    open_positions = [
        p for p in positions
        if (getattr(p, "status", "") or "").strip() in ("OPEN", "PARTIAL_EXIT")
        and not _exclude_diag(p)
    ]
    capital_in_use = sum(_capital_for_position(p) for p in open_positions)

    available = total_equity - capital_in_use
    available_clamped = False
    if available < 0:
        available = 0.0
        available_clamped = True

    util_pct = capital_in_use / total_equity if total_equity > 0 else 0.0

    # Build exposure dicts for risk flags
    exposure_by_symbol: Dict[str, float] = {}
    exposure_by_sector: Dict[str, float] = {}
    positions_by_sector: Dict[str, int] = {}

    for p in open_positions:
        sym = (getattr(p, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        cap = _capital_for_position(p)
        sector = get_sector(sym)
        exposure_by_symbol[sym] = exposure_by_symbol.get(sym, 0) + cap
        exposure_by_sector[sector] = exposure_by_sector.get(sector, 0) + cap
        positions_by_sector[sector] = positions_by_sector.get(sector, 0) + 1

    profile = risk_profile or load_risk_profile()
    risk_flags = evaluate_risk_flags(
        total_equity=total_equity,
        capital_in_use=capital_in_use,
        available_capital=available,
        open_positions_count=len(open_positions),
        exposure_by_symbol=exposure_by_symbol,
        exposure_by_sector=exposure_by_sector,
        profile=profile,
        positions_by_sector=positions_by_sector,
    )

    return PortfolioSummary(
        total_equity=total_equity,
        capital_in_use=capital_in_use,
        available_capital=available,
        capital_utilization_pct=util_pct,
        open_positions_count=len(open_positions),
        risk_flags=risk_flags,
        available_capital_clamped=available_clamped,
    )


def compute_exposure(
    accounts: List[Any],
    positions: List[Any],
    group_by: str = "symbol",
) -> List[Dict[str, Any]]:
    """
    Compute exposure by symbol or sector.

    group_by: "symbol" | "sector"
    Returns list of { key, required_capital, pct_of_total_equity, pct_of_available_capital, position_count }
    """
    total_equity = sum(float(getattr(a, "total_capital", 0) or 0) for a in accounts if getattr(a, "active", True))
    _exclude_diag = lambda p: (getattr(p, "symbol", "") or "").strip().upper().startswith("DIAG_TEST")
    open_positions = [
        p for p in positions
        if (getattr(p, "status", "") or "").strip() in ("OPEN", "PARTIAL_EXIT")
        and not _exclude_diag(p)
    ]
    capital_in_use = sum(_capital_for_position(p) for p in open_positions)
    available = max(0.0, total_equity - capital_in_use)

    agg: Dict[str, Dict[str, Any]] = {}
    for p in open_positions:
        sym = (getattr(p, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        cap = _capital_for_position(p)
        sector = get_sector(sym)
        key = sym if group_by == "symbol" else sector
        if key not in agg:
            agg[key] = {"required_capital": 0.0, "position_count": 0}
        agg[key]["required_capital"] += cap
        agg[key]["position_count"] += 1

    result = []
    for key, data in agg.items():
        rc = data["required_capital"]
        pct_equity = rc / total_equity if total_equity > 0 else 0.0
        pct_avail = rc / available if available > 0 else 0.0
        result.append({
            "key": key,
            "required_capital": round(rc, 2),
            "pct_of_total_equity": round(pct_equity, 4),
            "pct_of_available_capital": round(pct_avail, 4),
            "position_count": data["position_count"],
        })

    return sorted(result, key=lambda x: -x["required_capital"])
