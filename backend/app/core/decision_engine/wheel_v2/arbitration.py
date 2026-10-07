# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 CSP vs shares arbitration."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from app.core.decision_engine.contract import DecisionOutput, PortfolioState
from app.core.decision_engine.profiles import StrategyProfile
from app.core.decision_engine.wheel_v2.contract import (
    ASSIGNMENT_INAPPROPRIATE,
    BOTH_UNATTRACTIVE,
    CASH_INSUFFICIENT,
    CSP_PREFERRED,
    SHARES_PREFERRED,
    ArbitrationResult,
)


def _eligible(eval_obj: Any) -> bool:
    if eval_obj is None:
        return False
    if isinstance(eval_obj, DecisionOutput):
        return bool(eval_obj.eligibility) and (eval_obj.decision_status or "").upper() in (
            "ACTIONABLE",
            "WATCH",
        )
    if isinstance(eval_obj, Mapping):
        status = (eval_obj.get("decision_status") or eval_obj.get("status") or "").upper()
        if "eligibility" in eval_obj:
            elig = bool(eval_obj.get("eligibility"))
        else:
            elig = bool(eval_obj.get("eligible", False))
        if status:
            return elig and status in ("ACTIONABLE", "WATCH", "ELIGIBLE", "PASS")
        return elig
    return bool(getattr(eval_obj, "eligible", False) or getattr(eval_obj, "eligibility", False))


def _score(eval_obj: Any) -> float:
    if eval_obj is None:
        return -1.0
    if isinstance(eval_obj, DecisionOutput):
        return float(eval_obj.score or 0.0)
    if isinstance(eval_obj, Mapping):
        try:
            return float(eval_obj.get("score") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(getattr(eval_obj, "score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _capital_required(eval_obj: Any) -> float:
    if eval_obj is None:
        return 0.0
    if isinstance(eval_obj, DecisionOutput):
        return float(eval_obj.capital_required or 0.0)
    if isinstance(eval_obj, Mapping):
        for key in ("capital_required", "suggested_cost", "collateral"):
            v = eval_obj.get(key)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        sizing = eval_obj.get("sizing") or {}
        if isinstance(sizing, Mapping):
            for key in ("suggested_cost", "capital_required"):
                v = sizing.get(key)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
    return 0.0


def _cash(portfolio: Optional[Union[PortfolioState, Mapping[str, Any]]]) -> float:
    """CSP/shares collateral from trusted cash only — never total_capital or buying_power."""
    if portfolio is None:
        return 0.0
    if isinstance(portfolio, PortfolioState):
        return float(portfolio.available_cash or 0.0)
    if isinstance(portfolio, Mapping):
        if portfolio.get("balance_trusted") is False:
            return 0.0
        for key in ("available_cash", "cash"):
            v = portfolio.get(key)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
    return 0.0


def arbitrate_csp_vs_shares(
    csp_eval: Any,
    shares_eval: Any,
    portfolio: Optional[Union[PortfolioState, Mapping[str, Any]]] = None,
    profile: Optional[Union[StrategyProfile, Mapping[str, Any]]] = None,
    *,
    ownable: Optional[bool] = None,
) -> ArbitrationResult:
    """
    Choose CSP vs shares vs cash.

    Reason codes: CSP_PREFERRED, SHARES_PREFERRED, BOTH_UNATTRACTIVE,
    CASH_INSUFFICIENT, ASSIGNMENT_INAPPROPRIATE.
    ``profile`` is accepted for API symmetry (thresholds already applied upstream).
    """
    _ = profile  # portfolio-aware sizing already applied in evals; no retune here
    csp_ok = _eligible(csp_eval)
    shares_ok = _eligible(shares_eval)
    cash = _cash(portfolio)

    if ownable is False and csp_ok:
        # CSP that may assign into unwanted shares → prefer cash / shares skip CSP
        return ArbitrationResult(
            winner="CASH",
            loser="CSP",
            reason_codes=[ASSIGNMENT_INAPPROPRIATE, BOTH_UNATTRACTIVE],
            explanation_codes=["OWNABILITY_BLOCKED_CSP"],
        )

    csp_cap = _capital_required(csp_eval) if csp_ok else 0.0
    shares_cap = _capital_required(shares_eval) if shares_ok else 0.0

    if csp_ok and csp_cap > 0 and cash < csp_cap and not shares_ok:
        return ArbitrationResult(
            winner="CASH",
            loser="CSP",
            reason_codes=[CASH_INSUFFICIENT],
            explanation_codes=["CSP_COLLATERAL_EXCEEDS_CASH"],
        )
    if shares_ok and shares_cap > 0 and cash < shares_cap and not csp_ok:
        return ArbitrationResult(
            winner="CASH",
            loser="SHARES",
            reason_codes=[CASH_INSUFFICIENT],
            explanation_codes=["SHARES_COST_EXCEEDS_CASH"],
        )

    # Affordability filter
    if csp_ok and csp_cap > 0 and cash < csp_cap:
        csp_ok = False
    if shares_ok and shares_cap > 0 and cash < shares_cap:
        shares_ok = False

    if not csp_ok and not shares_ok:
        codes = [BOTH_UNATTRACTIVE]
        if cash <= 0:
            codes.append(CASH_INSUFFICIENT)
        return ArbitrationResult(
            winner="CASH",
            loser=None,
            reason_codes=codes,
            explanation_codes=["NO_ATTRACTIVE_ENTRY"],
        )

    if csp_ok and not shares_ok:
        return ArbitrationResult(
            winner="CSP",
            loser="SHARES",
            reason_codes=[CSP_PREFERRED],
            explanation_codes=["CSP_ONLY_ELIGIBLE"],
        )
    if shares_ok and not csp_ok:
        return ArbitrationResult(
            winner="SHARES",
            loser="CSP",
            reason_codes=[SHARES_PREFERRED],
            explanation_codes=["SHARES_ONLY_ELIGIBLE"],
        )

    # Both eligible: higher score wins; tie → CSP (wheel-first income bias, deterministic)
    csp_score = _score(csp_eval)
    shares_score = _score(shares_eval)
    if shares_score > csp_score:
        return ArbitrationResult(
            winner="SHARES",
            loser="CSP",
            reason_codes=[SHARES_PREFERRED],
            explanation_codes=["SHARES_HIGHER_SCORE"],
        )
    return ArbitrationResult(
        winner="CSP",
        loser="SHARES",
        reason_codes=[CSP_PREFERRED],
        explanation_codes=["CSP_HIGHER_OR_EQUAL_SCORE"],
    )
