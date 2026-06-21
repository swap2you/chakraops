# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Decision engine orchestration (R33.0).

Composes profiles, gates, strategies, sizing, and ranking into one advisory,
manual-only decision flow:

    inputs -> data-safety + eligibility gates -> strategy scoring -> sizing
           -> canonical output -> deterministic ranking

Hard gate failures (data/regime/earnings/liquidity/holdings/cash) => BLOCKED.
Soft failures (delta/DTE range, below-return-threshold, zero sizing) => WATCH.
Eligible + score >= profile threshold => ACTIONABLE. When nothing is
actionable, an explicit STAY_IN_CASH outcome is returned. No order is ever
created or routed; every output is labeled manual-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from app.core.decision_engine import gates as G
from app.core.decision_engine.contract import (
    ACTIONABLE,
    BLOCKED,
    CASH,
    COVERED_CALL,
    CSP,
    DQ_BLOCKED,
    DQ_DEGRADED,
    DQ_OK,
    DecisionInput,
    DecisionOutput,
    PortfolioState,
    SHARE_BUY,
    STAY_IN_CASH,
    WATCH,
)
from app.core.decision_engine.profiles import StrategyProfile, get_profile
from app.core.decision_engine.ranking import rank_outputs
from app.core.decision_engine.sizing import size_position
from app.core.decision_engine.strategies import evaluate_strategy


def _blocked(inp: DecisionInput, profile_name: str, reasons: List[str], freshness: dict) -> DecisionOutput:
    return DecisionOutput(
        symbol=inp.symbol,
        strategy=inp.strategy,
        profile=profile_name,
        market_regime=inp.market_regime,
        decision_status=BLOCKED,
        eligibility=False,
        data_quality=DQ_BLOCKED,
        data_freshness=freshness,
        event_risk={"earnings_days": inp.earnings_days},
        selected_contract=inp.contract.to_dict() if inp.contract else None,
        sizing={},
        capital_required=0.0,
        reason_codes=reasons,
    )


def evaluate_candidate(
    inp: DecisionInput,
    profile: StrategyProfile,
    *,
    portfolio: PortfolioState,
    now: Optional[datetime] = None,
) -> DecisionOutput:
    """Evaluate one (symbol, strategy) candidate into a canonical output."""
    now = now or datetime.now(timezone.utc)

    # 1) Data safety: stale / missing critical data blocks action (R32 gate).
    fresh = G.check_data_freshness(inp, now=now)
    freshness_payload = fresh.to_dict()
    if fresh.blocked:
        return _blocked(inp, profile.name, list(fresh.reason_codes), freshness_payload)

    ok, miss = G.check_missing_critical(inp)
    if not ok:
        return _blocked(inp, profile.name, miss, freshness_payload)

    # 2) Hard eligibility gates.
    ok, r = G.regime_gate(inp, profile)
    if not ok:
        return _blocked(inp, profile.name, r, freshness_payload)
    ok, r = G.earnings_gate(inp, profile)
    if not ok:
        return _blocked(inp, profile.name, r, freshness_payload)
    ok, r = G.liquidity_gate(inp, profile)
    if not ok:
        return _blocked(inp, profile.name, r, freshness_payload)
    ok, r = G.holdings_gate(inp)
    if not ok:
        return _blocked(inp, profile.name, r, freshness_payload)

    cash_buffer_amount = portfolio.total_value * profile.cash_buffer_pct / 100.0
    available_after_buffer = max(0.0, portfolio.available_cash - cash_buffer_amount)
    ok, r = G.cash_gate(inp, profile, available_after_buffer)
    if not ok:
        return _blocked(inp, profile.name, r, freshness_payload)

    # 3) Strategy scoring + sizing.
    seval = evaluate_strategy(inp, profile)
    sized = size_position(inp, profile, portfolio)

    # 4) Expected return.
    expected_return_pct = seval.return_pct
    expected_return_dollars = None
    if inp.contract is not None and inp.strategy in (CSP, COVERED_CALL):
        expected_return_dollars = round(inp.contract.premium * 100.0 * sized.sizing.contracts, 2)
    elif inp.strategy == SHARE_BUY:
        expected_return_pct = None  # share buys have no premium yield

    # 5) Status.
    eligible = seval.passed_strategy_rules and sized.is_actionable
    if eligible and seval.score >= profile.actionable_min_score:
        status = ACTIONABLE
    else:
        status = WATCH

    reason_codes = list(seval.positive_reasons) + list(seval.soft_reasons)
    risk_flags = list(seval.risk_flags) + list(sized.risk_flags)
    if not sized.is_actionable and "ZERO_SIZE" not in reason_codes:
        reason_codes.append("ZERO_SIZE")

    data_quality = DQ_DEGRADED if risk_flags else DQ_OK

    return DecisionOutput(
        symbol=inp.symbol,
        strategy=inp.strategy,
        profile=profile.name,
        market_regime=inp.market_regime,
        decision_status=status,
        eligibility=eligible,
        data_quality=data_quality,
        data_freshness=freshness_payload,
        event_risk={"earnings_days": inp.earnings_days, "blackout_days": profile.earnings_blackout_days},
        selected_contract=inp.contract.to_dict() if inp.contract else None,
        sizing=sized.sizing.to_dict(),
        capital_required=sized.capital_required,
        expected_return_pct=expected_return_pct,
        expected_return_dollars=expected_return_dollars,
        risk_flags=risk_flags,
        score=seval.score,
        reason_codes=reason_codes,
    )


def _stay_in_cash(profile_name: str, regime: str, reason: str) -> DecisionOutput:
    return DecisionOutput(
        symbol="-",
        strategy=CASH,
        profile=profile_name,
        market_regime=regime,
        decision_status=STAY_IN_CASH,
        eligibility=True,
        data_quality=DQ_OK,
        reason_codes=[reason],
        score=0.0,
    )


def evaluate(
    inputs: List[DecisionInput],
    *,
    profile_name: str = "balanced",
    portfolio: PortfolioState,
    now: Optional[datetime] = None,
    profile_overrides: Optional[dict] = None,
) -> dict:
    """Evaluate a batch of candidates and return ranked, partitioned advice.

    Output keys: ``profile``, ``actionable`` (ranked, capped to top 5–7),
    ``watch``, ``blocked``, ``stay_in_cash`` (explicit outcome with reason),
    and ``counts``. Manual-only; advisory.
    """
    profile = get_profile(profile_name, overrides=profile_overrides)
    now = now or datetime.now(timezone.utc)

    outputs = [evaluate_candidate(i, profile, portfolio=portfolio, now=now) for i in inputs]
    total_actionable = sum(1 for o in outputs if o.decision_status == ACTIONABLE)
    partitioned = rank_outputs(outputs, profile.max_recommendations)

    actionable = partitioned["actionable"]
    market_regime = inputs[0].market_regime if inputs else "UNKNOWN"
    if actionable:
        stay = _stay_in_cash(profile.name, market_regime, "CASH_IS_FALLBACK_NOT_REQUIRED")
    else:
        stay = _stay_in_cash(profile.name, market_regime, "NO_ACTIONABLE_CANDIDATES")

    return {
        "profile": profile.to_dict(),
        "as_of_utc": now.astimezone(timezone.utc).isoformat(),
        "manual_only": True,
        "actionable": [o.to_dict() for o in actionable],
        "watch": [o.to_dict() for o in partitioned["watch"]],
        "blocked": [o.to_dict() for o in partitioned["blocked"]],
        "stay_in_cash": stay.to_dict(),
        "counts": {
            "actionable": total_actionable,
            "shown": len(actionable),
            "watch": len(partitioned["watch"]),
            "blocked": len(partitioned["blocked"]),
            "total_candidates": len(inputs),
        },
    }
