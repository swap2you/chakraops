# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.1: Portfolio Snapshot Engine — calculation only.

Read-only calculations from open positions ledger. Produces portfolio statistics
for operator awareness. Does NOT mutate signals, sizing, or trading logic.
Non-mutation guarantee: this module only reads data and computes aggregates;
it never modifies positions, evaluator state, or broker data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Use same default path as Phase 7.1 position ledger
from app.core.positions.position_ledger import load_open_positions as _load_open_positions

# Phase 8.6: Static sector/cluster mapping
from app.core.portfolio.cluster_mapper import get_symbol_tags, load_cluster_map

# Threshold for "near ITM" assignment risk: spot <= strike * 1.02 (within 2%)
ASSIGNMENT_RISK_NEAR_ITM_THRESHOLD = 1.02

# Phase 8.6: sector_breakdown OK threshold (>= 80% of positions tagged)
SECTOR_TAGGED_THRESHOLD = 0.80


def _parse_date(value: Any) -> Optional[date]:
    """Parse date from str or date/datetime. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _position_mode(pos: Dict[str, Any]) -> str:
    """Normalize position mode/type to CSP or CC."""
    m = (pos.get("mode") or pos.get("type") or "CSP").strip().upper()
    return "CC" if m == "CC" else "CSP"


def _position_committed(pos: Dict[str, Any], warnings: List[str]) -> float:
    """
    Compute committed capital for one position.

    CSP: strike * 100 * contracts
    CC: shares * (cost_basis_per_share or entry_spot). If shares/cost missing, 0 + warning.
    """
    mode = _position_mode(pos)
    contracts = int(pos.get("contracts") or 0)

    if mode == "CSP":
        strike = pos.get("strike")
        if strike is None:
            return 0.0
        return float(strike) * 100 * max(0, contracts)

    # CC: shares * cost
    shares = pos.get("shares") or pos.get("quantity")
    if shares is None:
        # CC: 1 contract = 100 shares
        shares = contracts * 100
    else:
        shares = int(shares)
    cost = pos.get("cost_basis_per_share") or pos.get("entry_spot")
    if cost is None:
        warnings.append("CC position %s missing shares/cost_basis; committed=0" % (pos.get("symbol") or pos.get("position_id", "?")))
        return 0.0
    if shares <= 0:
        return 0.0
    return float(shares) * float(cost)


@dataclass
class PortfolioSnapshot:
    """Phase 8.1: Portfolio snapshot — read-only aggregation from open positions."""

    as_of: str
    total_open_positions: int
    open_csp_count: int
    open_cc_count: int
    total_capital_committed: float
    exposure_pct: Optional[float]
    avg_premium_capture: Optional[float]
    weighted_dte: Optional[float]
    assignment_risk: Dict[str, Any]
    symbol_concentration: Dict[str, Any]
    sector_breakdown: Dict[str, Any]
    cluster_risk_level: str
    cluster_breakdown: Dict[str, Any]  # Phase 8.6
    max_cluster_pct: Optional[float]  # Phase 8.6
    regime_adjusted_exposure: Optional[float]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of,
            "total_open_positions": self.total_open_positions,
            "open_csp_count": self.open_csp_count,
            "open_cc_count": self.open_cc_count,
            "total_capital_committed": self.total_capital_committed,
            "exposure_pct": self.exposure_pct,
            "avg_premium_capture": self.avg_premium_capture,
            "weighted_dte": self.weighted_dte,
            "assignment_risk": self.assignment_risk,
            "symbol_concentration": self.symbol_concentration,
            "sector_breakdown": self.sector_breakdown,
            "cluster_risk_level": self.cluster_risk_level,
            "cluster_breakdown": self.cluster_breakdown,
            "max_cluster_pct": self.max_cluster_pct,
            "regime_adjusted_exposure": self.regime_adjusted_exposure,
            "warnings": list(self.warnings),
        }


def get_portfolio_equity_usd() -> Optional[float]:
    """
    Read portfolio equity from config/env. Used for exposure_pct.

    Priority: PORTFOLIO_EQUITY_USD env, then ACCOUNT_EQUITY env,
    then get_account_equity() (scoring/config/accounts).
    """
    for env_var in ("PORTFOLIO_EQUITY_USD", "ACCOUNT_EQUITY"):
        val = os.getenv(env_var)
        if val is not None:
            try:
                f = float(val)
                if f > 0:
                    return f
            except ValueError:
                pass
    try:
        from app.core.eval.scoring import get_account_equity
        eq = get_account_equity()
        if eq is not None and eq > 0:
            return eq
    except ImportError:
        pass
    return None


def load_open_positions(path: Union[str, Path, None] = None) -> List[Dict[str, Any]]:
    """
    Load open positions from ledger. Thin wrapper around position_ledger.

    Args:
        path: Ledger path; defaults to artifacts/positions/open_positions.json
    """
    return _load_open_positions(path)


def build_portfolio_snapshot(
    positions: List[Dict[str, Any]],
    portfolio_equity_usd: Optional[float],
    regime_state: Optional[Dict[str, Any]] = None,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Build portfolio snapshot from positions. Read-only; does not mutate inputs.

    Args:
        positions: List of position dicts (from load_open_positions or caller-provided).
        portfolio_equity_usd: Account/portfolio equity for exposure_pct. None → exposure_pct and
            regime_adjusted_exposure are None; warning added if positions exist.
        regime_state: Optional dict with throttle_factor (e.g. 0.8) for regime_adjusted_exposure.
        as_of: Snapshot timestamp; defaults to now.

    Returns:
        Snapshot dict with all Phase 8.1 fields.
    """
    warnings: List[str] = []
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    as_of_str = as_of.isoformat() if isinstance(as_of, datetime) else str(as_of)
    today = as_of.date() if isinstance(as_of, datetime) else date.today()

    total = len(positions)
    csp_count = sum(1 for p in positions if _position_mode(p) == "CSP")
    cc_count = sum(1 for p in positions if _position_mode(p) == "CC")

    # Committed capital per position
    committed_list: List[float] = []
    for p in positions:
        c = _position_committed(p, warnings)
        committed_list.append(c)
    total_committed = sum(committed_list)

    if portfolio_equity_usd is None and total > 0:
        warnings.append("PORTFOLIO_EQUITY_USD missing; exposure_pct and regime_adjusted_exposure unavailable")
    exposure_pct: Optional[float] = None
    if portfolio_equity_usd is not None and portfolio_equity_usd > 0:
        exposure_pct = 100.0 * total_committed / float(portfolio_equity_usd)

    # avg_premium_capture: from position.premium_capture_pct if present (e.g. from merged eval data)
    captures = [
        float(p["premium_capture_pct"])
        for p in positions
        if p.get("premium_capture_pct") is not None
    ]
    avg_premium_capture: Optional[float] = sum(captures) / len(captures) if captures else None

    # weighted_dte: DTE weighted by committed (or contracts if committed=0).
    # Prefer numeric dte when present (timezone-safe). Else compute from expiry using UTC date-only.
    as_of_date = today  # already date in UTC when as_of was datetime.utc
    dte_weights: List[tuple] = []
    for i, p in enumerate(positions):
        dte_val: Optional[int] = None
        # 1. Prefer explicit numeric dte
        raw_dte = p.get("dte")
        if raw_dte is not None:
            try:
                d = int(float(raw_dte))
                if d >= 0:
                    dte_val = d
            except (TypeError, ValueError):
                pass
        # 2. Else compute from expiry (date-only arithmetic, UTC)
        if dte_val is None:
            exp = _parse_date(p.get("expiration") or p.get("expiry"))
            if exp is None:
                warnings.append("Position %s missing dte and expiration; skipped for weighted_dte" % (p.get("symbol") or p.get("position_id", "?")))
                continue
            dte_val = max(0, (exp - as_of_date).days)
        w = committed_list[i] if i < len(committed_list) else 0
        if w <= 0:
            w = float(p.get("contracts") or 1)
        dte_weights.append((dte_val, w))
    weighted_dte_val: Optional[float] = None
    if dte_weights and sum(w for _, w in dte_weights) > 0:
        total_w = sum(w for _, w in dte_weights)
        weighted_dte_val = sum(d * w for d, w in dte_weights) / total_w

    # symbol_concentration: top 5 symbols by committed
    symbol_committed: Dict[str, float] = {}
    for i, p in enumerate(positions):
        sym = (p.get("symbol") or "?").strip().upper()
        c = committed_list[i] if i < len(committed_list) else 0
        symbol_committed[sym] = symbol_committed.get(sym, 0) + c
    top_symbols = sorted(symbol_committed.items(), key=lambda x: -x[1])[:5]
    top_list = [
        {"symbol": s, "committed": c, "pct_of_committed": 100.0 * c / total_committed if total_committed > 0 else 0}
        for s, c in top_symbols
    ]
    max_symbol_pct: Optional[float] = max((p["pct_of_committed"] for p in top_list), default=None) if top_list else None
    symbol_concentration = {"top_symbols": top_list, "max_symbol_pct": max_symbol_pct}

    # Phase 8.6: Load cluster map override (if exists)
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _cluster_map_path = _repo_root / "artifacts" / "config" / "cluster_map.json"
    cluster_map_override = load_cluster_map(_cluster_map_path) if _cluster_map_path else {}

    # sector_breakdown: use position sector or mapped sector from get_symbol_tags
    sectors: Dict[str, float] = {}
    tagged_sector_count = 0
    for i, p in enumerate(positions):
        sec_raw = p.get("sector")
        if sec_raw is not None and isinstance(sec_raw, str) and sec_raw.strip():
            sec = sec_raw.strip()
        else:
            tags = get_symbol_tags(p.get("symbol") or "?", cluster_map_override or None)
            sec = tags.get("sector") or "UNKNOWN"
        if sec and sec != "UNKNOWN":
            tagged_sector_count += 1
        sec = sec or "UNKNOWN"
        c = committed_list[i] if i < len(committed_list) else 0
        sectors[sec] = sectors.get(sec, 0) + c
    pct_tagged = tagged_sector_count / total if total > 0 else 0.0
    if tagged_sector_count == 0:
        sector_status = "UNKNOWN"
        by_sector: List[Dict[str, Any]] = []
    elif pct_tagged < SECTOR_TAGGED_THRESHOLD:
        sector_status = "PARTIAL"
        by_sector = [
            {"sector": s, "committed": c, "pct_of_committed": 100.0 * c / total_committed}
            for s, c in sorted(sectors.items(), key=lambda x: -x[1])
        ]
    else:
        sector_status = "OK"
        by_sector = [
            {"sector": s, "committed": c, "pct_of_committed": 100.0 * c / total_committed}
            for s, c in sorted(sectors.items(), key=lambda x: -x[1])
        ]
    sector_breakdown = {"status": sector_status, "by_sector": by_sector}

    # assignment_risk: CSP with spot and strike (within 2% of ITM)
    positions_near_itm: Optional[int] = None
    notional_itm_risk: Optional[float] = None
    assignment_status = "UNKNOWN"
    near_itm_committed: List[float] = []
    has_any_csp_spot_strike = False
    for i, p in enumerate(positions):
        if _position_mode(p) != "CSP":
            continue
        spot = p.get("spot") or p.get("entry_spot") or p.get("current_spot")
        strike = p.get("strike")
        if spot is None or strike is None:
            continue
        has_any_csp_spot_strike = True
        spot_f = float(spot)
        strike_f = float(strike)
        if strike_f <= 0:
            continue
        if spot_f <= strike_f * ASSIGNMENT_RISK_NEAR_ITM_THRESHOLD:
            c = committed_list[i] if i < len(committed_list) else 0
            near_itm_committed.append(c)
    if has_any_csp_spot_strike:
        assignment_status = "ESTIMATED"
        positions_near_itm = len(near_itm_committed)
        notional_itm_risk = sum(near_itm_committed) if near_itm_committed else 0.0
    assignment_risk = {
        "status": assignment_status,
        "notional_itm_risk": notional_itm_risk,
        "positions_near_itm": positions_near_itm,
    }

    # Phase 8.6: cluster from position or mapped; cluster_breakdown + cluster_risk_level
    cluster_counts: Dict[str, int] = {}
    cluster_committed: Dict[str, float] = {}
    has_cluster = False
    tagged_cluster_count = 0
    for i, p in enumerate(positions):
        cl = p.get("cluster")
        if cl is None or not isinstance(cl, str) or not (cl and cl.strip()):
            tags = get_symbol_tags(p.get("symbol") or "?", cluster_map_override or None)
            cl = tags.get("cluster") or "UNKNOWN"
        else:
            cl = cl.strip() or "?"
        if cl and cl != "UNKNOWN":
            has_cluster = True
            tagged_cluster_count += 1
        cl = cl or "UNKNOWN"
        cluster_counts[cl] = cluster_counts.get(cl, 0) + 1
        c = committed_list[i] if i < len(committed_list) else 0
        cluster_committed[cl] = cluster_committed.get(cl, 0) + c
    cluster_risk_level = "UNKNOWN"
    if has_cluster and cluster_counts:
        max_count = max(cluster_counts.values())
        if max_count >= 3:
            cluster_risk_level = "HIGH"
        elif max_count == 2:
            cluster_risk_level = "MEDIUM"
        else:
            cluster_risk_level = "LOW"
    pct_cluster_tagged = tagged_cluster_count / total if total > 0 else 0.0
    if tagged_cluster_count == 0:
        cluster_breakdown_status = "UNKNOWN"
    elif pct_cluster_tagged < SECTOR_TAGGED_THRESHOLD:
        cluster_breakdown_status = "PARTIAL"
    else:
        cluster_breakdown_status = "OK"
    by_cluster = [
        {
            "cluster": k,
            "count": cluster_counts[k],
            "committed": v,
            "pct_of_committed": 100.0 * v / total_committed if total_committed > 0 else 0,
        }
        for k, v in sorted(cluster_committed.items(), key=lambda x: -x[1])
    ]
    cluster_breakdown = {"status": cluster_breakdown_status, "by_cluster": by_cluster}
    max_cluster_pct_val: Optional[float] = max(
        (b["pct_of_committed"] for b in by_cluster), default=None
    ) if by_cluster else None

    # regime_adjusted_exposure
    regime_adjusted_exposure: Optional[float] = None
    rs = regime_state or {}
    throttle = rs.get("throttle_factor")
    if throttle is not None and exposure_pct is not None:
        try:
            regime_adjusted_exposure = exposure_pct * float(throttle)
        except (TypeError, ValueError):
            pass

    snapshot = PortfolioSnapshot(
        as_of=as_of_str,
        total_open_positions=total,
        open_csp_count=csp_count,
        open_cc_count=cc_count,
        total_capital_committed=total_committed,
        exposure_pct=exposure_pct,
        avg_premium_capture=avg_premium_capture,
        weighted_dte=weighted_dte_val,
        assignment_risk=assignment_risk,
        symbol_concentration=symbol_concentration,
        sector_breakdown=sector_breakdown,
        cluster_risk_level=cluster_risk_level,
        cluster_breakdown=cluster_breakdown,
        max_cluster_pct=max_cluster_pct_val,
        regime_adjusted_exposure=regime_adjusted_exposure,
        warnings=warnings,
    )
    return snapshot.to_dict()
