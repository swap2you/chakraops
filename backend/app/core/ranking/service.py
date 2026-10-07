# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2A: Ranking service — produce ranked opportunities from evaluation data.

Answers: "If I can only take a few trades, which ones matter most right now — and why?"

Ranking rules (strict order):
  1. Band priority: A > B > C
  2. Composite score (descending)
  3. Capital efficiency: (capital_required / account_equity) ascending
  4. Liquidity sanity check (soft penalty only)

Strategy exclusivity:
  - Each symbol surfaces only ONE primary strategy
  - CSP if CSP-eligible
  - CC only if shares exist (position_open=True)
  - STOCK if neither CSP nor CC is valid
  - Never show CSP + CC simultaneously for same symbol
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Band sort priority (lower = better)
_BAND_PRIORITY = {"A": 0, "B": 1, "C": 2}


def _get_band(sym: Dict[str, Any]) -> str:
    """Extract band from capital_hint or score_breakdown."""
    hint = sym.get("capital_hint")
    if hint and isinstance(hint, dict):
        return hint.get("band", "C")
    # Fallback: derive from composite score
    score = sym.get("score", 0)
    if score >= 78:
        return "A"
    elif score >= 60:
        return "B"
    return "C"


def _get_composite_score(sym: Dict[str, Any]) -> int:
    """Extract final (post-cap) score. Phase 10.1: use score/final_score only, not pre-cap composite."""
    s = sym.get("final_score") or sym.get("score")
    if s is not None:
        return int(s)
    bd = sym.get("score_breakdown")
    if bd and isinstance(bd, dict):
        return int(bd.get("final_score", bd.get("composite_score", 0)))
    return int(sym.get("score", 0))


def _get_primary_strategy(sym: Dict[str, Any]) -> Optional[str]:
    """Determine the single primary strategy for a symbol.

    Strategy exclusivity:
      - CSP if any CSP candidate trade exists
      - CC only if position_open is True and CC candidate exists
      - STOCK if neither CSP nor CC
      - None if no actionable strategy (e.g., HOLD)
    """
    candidates = sym.get("candidate_trades", [])
    has_csp = any(t.get("strategy") == "CSP" for t in candidates)
    has_cc = any(t.get("strategy") == "CC" for t in candidates)
    position_open = sym.get("position_open", False)

    if has_csp:
        return "CSP"
    if has_cc and position_open:
        return "CC"
    # STOCK only if explicitly suggested
    has_stock = any(t.get("strategy") == "STOCK" for t in candidates)
    if has_stock:
        return "STOCK"
    # No actionable strategy
    return None


def _get_primary_candidate_trade(sym: Dict[str, Any], strategy: str) -> Optional[Dict[str, Any]]:
    """Get the first candidate trade matching the primary strategy."""
    candidates = sym.get("candidate_trades", [])
    for t in candidates:
        if t.get("strategy") == strategy:
            return t
    return None


def _compute_capital_required(sym: Dict[str, Any], strategy: str, trade: Optional[Dict[str, Any]]) -> Optional[float]:
    """Compute capital required for the primary strategy."""
    if strategy == "CSP":
        # CSP notional = strike * 100
        strike = None
        if trade:
            strike = trade.get("strike")
        if strike is None:
            # Try from selected contract
            sc = sym.get("selected_contract")
            if sc and isinstance(sc, dict):
                contract = sc.get("contract", {})
                strike = contract.get("strike")
        if strike is None:
            # Fallback from csp_notional
            notional = sym.get("csp_notional")
            if notional and notional > 0:
                return float(notional)
            return None
        return float(strike) * 100
    elif strategy == "CC":
        # CC capital = 100 shares * price (already held)
        price = sym.get("price")
        if price and price > 0:
            return float(price) * 100
        return None
    elif strategy == "STOCK":
        price = sym.get("price")
        if price and price > 0:
            return float(price) * 100  # 100 shares default
        return None
    return None


def _build_rank_reason(
    band: str,
    score: int,
    strategy: str,
    capital_pct: Optional[float],
    liquidity_ok: bool,
    primary_reason: str,
) -> str:
    """Build human-readable rank reason."""
    parts: List[str] = []
    parts.append(f"Band {band}")
    parts.append(f"score {score}")
    if capital_pct is not None:
        if capital_pct < 0.05:
            parts.append("efficient capital use")
        elif capital_pct < 0.10:
            parts.append("moderate capital use")
        else:
            parts.append(f"capital {capital_pct:.0%}")
    if not liquidity_ok:
        parts.append("liquidity caution")
    return ", ".join(parts)


def _apply_risk_status(
    opportunity: Dict[str, Any],
    risk_context: Optional[Dict[str, Any]],
) -> None:
    """Phase 3: Add risk_status (OK/BLOCKED/WARN) and risk_reasons to opportunity."""
    opportunity["risk_status"] = "OK"
    opportunity["risk_reasons"] = []
    if not risk_context:
        return
    try:
        from app.core.portfolio.risk import would_exceed_limits
        from app.core.market.company_data import get_sector

        profile = risk_context.get("profile")
        total_equity = risk_context.get("total_equity", 0)
        capital_in_use = risk_context.get("capital_in_use", 0)
        exposure_by_symbol = risk_context.get("exposure_by_symbol", {})
        exposure_by_sector = risk_context.get("exposure_by_sector", {})
        positions_by_sector = risk_context.get("positions_by_sector", {})
        open_positions_count = risk_context.get("open_positions_count", 0)

        sym = opportunity.get("symbol", "")
        cap = opportunity.get("capital_required") or 0.0
        sector = get_sector(sym)

        if profile and total_equity > 0:
            would_exceed, reasons = would_exceed_limits(
                profile=profile,
                total_equity=total_equity,
                capital_in_use=capital_in_use,
                open_positions_count=open_positions_count,
                exposure_by_symbol=exposure_by_symbol,
                exposure_by_sector=exposure_by_sector,
                positions_by_sector=positions_by_sector,
                candidate_symbol=sym,
                candidate_capital=cap,
                candidate_sector=sector,
            )
            if would_exceed and reasons:
                opportunity["risk_status"] = "BLOCKED"
                opportunity["risk_reasons"] = reasons
            else:
                # Soft warn: nearing thresholds (e.g. util > 0.8 * max)
                util = (capital_in_use + cap) / total_equity if total_equity > 0 else 0
                max_util = profile.max_capital_utilization_pct if profile else 0.35
                if max_util > 0 and util > max_util * 0.85 and util <= max_util:
                    opportunity["risk_status"] = "WARN"
                    opportunity["risk_reasons"] = [f"Nearing max utilization ({util:.1%} of {max_util:.1%})"]
    except Exception as e:
        logger.debug("[RANKING] Risk check failed: %s", e)


def rank_opportunities(
    symbols: List[Dict[str, Any]],
    account_equity: Optional[float] = None,
    limit: int = 5,
    strategy_filter: Optional[str] = None,
    max_capital_pct: Optional[float] = None,
    include_blocked: bool = False,
    risk_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Produce a ranked list of opportunities from evaluation symbols.

    Args:
        symbols: Per-symbol dicts from an evaluation run.
        account_equity: Account total capital (from default account). None means no capital filtering.
        limit: Max results to return.
        strategy_filter: Only include this strategy (CSP, CC, STOCK).
        max_capital_pct: Only include opportunities where capital_pct <= this value (0.0-1.0).
        include_blocked: If True, include BLOCKED opportunities with risk_reasons. If False, exclude them.
        risk_context: Phase 3: Optional dict for risk-aware ranking (profile, total_equity, etc.).

    Returns:
        List of RankedOpportunity dicts, sorted by rank. Each includes risk_status and risk_reasons.
    """
    opportunities: List[Dict[str, Any]] = []

    for sym in symbols:
        # Only ELIGIBLE symbols become opportunities
        verdict = sym.get("verdict", "")
        if verdict != "ELIGIBLE":
            continue

        # Determine primary strategy (exclusivity)
        strategy = _get_primary_strategy(sym)
        if strategy is None:
            continue

        # Strategy filter
        if strategy_filter and strategy != strategy_filter:
            continue

        # Get the primary candidate trade
        trade = _get_primary_candidate_trade(sym, strategy)

        # Band and score
        band = _get_band(sym)
        score = _get_composite_score(sym)

        # Capital computation
        capital_required = _compute_capital_required(sym, strategy, trade)
        capital_pct: Optional[float] = None
        if capital_required is not None and account_equity and account_equity > 0:
            capital_pct = capital_required / account_equity

        # Capital filter
        if max_capital_pct is not None and capital_pct is not None:
            if capital_pct > max_capital_pct:
                continue

        # Liquidity
        liquidity_ok = sym.get("liquidity_ok", True)

        # Build rank reason
        rank_reason = _build_rank_reason(
            band, score, strategy, capital_pct, liquidity_ok,
            sym.get("primary_reason", ""),
        )

        # Extract trade details
        strike = trade.get("strike") if trade else None
        expiry = trade.get("expiry") if trade else None
        credit_estimate = trade.get("credit_estimate") if trade else None
        delta = trade.get("delta") if trade else None

        # Selected contract enrichment
        selected_contract = sym.get("selected_contract")
        if selected_contract and isinstance(selected_contract, dict):
            contract = selected_contract.get("contract", {})
            if strike is None:
                strike = contract.get("strike")
            if expiry is None:
                expiry = contract.get("expiration")
            if delta is None:
                delta = contract.get("delta")
            if credit_estimate is None:
                bid = contract.get("bid")
                if bid is not None:
                    credit_estimate = float(bid)

        # Phase 6: Data dependency enforcement — BLOCK when required data missing
        required_data_missing: List[str] = []
        optional_data_missing: List[str] = []
        required_data_stale: List[str] = []
        data_as_of: Dict[str, Optional[str]] = {}
        try:
            from app.core.symbols.data_dependencies import compute_dependency_lists
            sym_dict = sym if isinstance(sym, dict) else {k: getattr(sym, k, None) for k in ("symbol", "price", "bid", "ask", "volume", "avg_option_volume_20d", "avg_stock_volume_20d", "iv_rank", "quote_date", "fetched_at", "verdict", "candidate_trades", "selected_contract")}
            required_data_missing, optional_data_missing, required_data_stale, data_as_of = compute_dependency_lists(sym_dict)
        except Exception as e:
            logger.debug("[RANKING] Data dependency check failed: %s", e)
            required_data_missing = ["dependency_check_error"]

        opportunity: Dict[str, Any] = {
            "symbol": sym.get("symbol", ""),
            "strategy": strategy,
            "band": band,
            "score": score,
            "capital_required": capital_required,
            "capital_pct": round(capital_pct, 4) if capital_pct is not None else None,
            "rank_reason": rank_reason,
            "primary_reason": sym.get("primary_reason", ""),
            "price": sym.get("price"),
            "strike": strike,
            "expiry": expiry,
            "credit_estimate": credit_estimate,
            "delta": delta,
            "liquidity_ok": liquidity_ok,
            "position_open": sym.get("position_open", False),
            "data_completeness": sym.get("data_completeness"),
            "stage_reached": sym.get("stage_reached"),
            "score_breakdown": sym.get("score_breakdown"),
            "rank_reasons": sym.get("rank_reasons"),
            "required_data_missing": required_data_missing,
            "optional_data_missing": optional_data_missing,
            "required_data_stale": required_data_stale,
            "data_as_of_orats": data_as_of.get("data_as_of_orats"),
            "data_as_of_price": data_as_of.get("data_as_of_price"),
        }

        # Phase 6: Required data missing → BLOCKED (takes precedence over portfolio risk)
        if required_data_missing:
            opportunity["risk_status"] = "BLOCKED"
            opportunity["risk_reasons"] = ["Required data missing: " + ", ".join(required_data_missing)]
        else:
            _apply_risk_status(opportunity, risk_context)

        # Exclude BLOCKED unless include_blocked
        if not include_blocked and opportunity.get("risk_status") == "BLOCKED":
            continue

        opportunities.append(opportunity)

    # Sort: Band priority (A>B>C), then score descending, then capital_pct ascending
    opportunities.sort(key=lambda o: (
        _BAND_PRIORITY.get(o["band"], 99),
        -o["score"],
        o["capital_pct"] if o["capital_pct"] is not None else 999.0,
        # Liquidity tiebreaker: prefer liquid
        0 if o["liquidity_ok"] else 1,
    ))

    # Assign rank
    for i, opp in enumerate(opportunities):
        opp["rank"] = i + 1

    return opportunities[:limit]


def get_dashboard_opportunities(
    limit: int = 5,
    strategy_filter: Optional[str] = None,
    max_capital_pct: Optional[float] = None,
    include_blocked: bool = False,
) -> Dict[str, Any]:
    """Load latest evaluation and produce ranked opportunities.

    Args:
        include_blocked: Phase 3 — If True, include BLOCKED opportunities with risk_reasons.

    Returns:
        {
            "opportunities": [...],  # each has risk_status, risk_reasons
            "count": int,
            "evaluation_id": str | None,
            "evaluated_at": str | None,
            "account_equity": float | None,
            "total_eligible": int,
        }
    """
    # Load latest evaluation run
    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
    except Exception as e:
        logger.warning("[RANKING] Failed to load latest run: %s", e)
        return {
            "opportunities": [],
            "count": 0,
            "evaluation_id": None,
            "evaluated_at": None,
            "account_equity": None,
            "total_eligible": 0,
            "error": str(e),
        }

    if run is None:
        return {
            "opportunities": [],
            "count": 0,
            "evaluation_id": None,
            "evaluated_at": None,
            "account_equity": None,
            "total_eligible": 0,
        }

    symbols = run.symbols or []

    # Get account equity from default account
    account_equity: Optional[float] = None
    try:
        from app.core.accounts.service import get_default_account
        default_acct = get_default_account()
        if default_acct and default_acct.total_capital > 0:
            account_equity = default_acct.total_capital
    except ImportError:
        pass

    # Count total eligible
    total_eligible = sum(1 for s in symbols if s.get("verdict") == "ELIGIBLE")

    # Phase 3: Build risk context for risk-aware ranking
    risk_context: Optional[Dict[str, Any]] = None
    try:
        from app.core.accounts.store import list_accounts
        from app.core.positions.store import list_positions
        from app.core.portfolio.store import load_risk_profile
        from app.core.market.company_data import get_sector

        accounts = list_accounts()
        positions = list_positions()
        profile = load_risk_profile()
        total_equity = sum(float(a.total_capital or 0) for a in accounts if getattr(a, "active", True))
        open_positions = [p for p in positions if (p.status or "").strip() in ("OPEN", "PARTIAL_EXIT")]
        capital_in_use = 0.0
        exposure_by_symbol: Dict[str, float] = {}
        exposure_by_sector: Dict[str, float] = {}
        positions_by_sector: Dict[str, int] = {}
        for p in open_positions:
            sym = (p.symbol or "").strip().upper()
            if not sym:
                continue
            cap = (float(p.strike or 0) * 100 * int(p.contracts or 0)) if (p.strategy or "").strip() == "CSP" else 0.0
            sector = get_sector(sym)
            capital_in_use += cap
            exposure_by_symbol[sym] = exposure_by_symbol.get(sym, 0) + cap
            exposure_by_sector[sector] = exposure_by_sector.get(sector, 0) + cap
            positions_by_sector[sector] = positions_by_sector.get(sector, 0) + 1
        risk_context = {
            "profile": profile,
            "total_equity": total_equity,
            "capital_in_use": capital_in_use,
            "exposure_by_symbol": exposure_by_symbol,
            "exposure_by_sector": exposure_by_sector,
            "positions_by_sector": positions_by_sector,
            "open_positions_count": len(open_positions),
        }
    except Exception as e:
        logger.debug("[RANKING] Failed to build risk context: %s", e)

    # Rank
    opportunities = rank_opportunities(
        symbols=symbols,
        account_equity=account_equity,
        limit=limit * 2 if include_blocked else limit,  # fetch more if including blocked
        strategy_filter=strategy_filter,
        max_capital_pct=max_capital_pct,
        include_blocked=include_blocked,
        risk_context=risk_context,
    )
    opportunities = opportunities[:limit]

    return {
        "opportunities": opportunities,
        "count": len(opportunities),
        "evaluation_id": run.run_id,
        "evaluated_at": run.completed_at,
        "account_equity": account_equity,
        "total_eligible": total_eligible,
    }
