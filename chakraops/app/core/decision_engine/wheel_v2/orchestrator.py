# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Wheel V2 orchestrator — evaluate_wheel_v2 → WheelDecisionV2."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union

from app.core.decision_engine.profiles import StrategyProfile, get_profile
from app.core.decision_engine.wheel_v2.assignment import assignment_advisory
from app.core.decision_engine.wheel_v2.arbitration import arbitrate_csp_vs_shares
from app.core.decision_engine.wheel_v2.contract import ManualPlan, WheelDecisionV2
from app.core.decision_engine.wheel_v2.management import manage_open_option
from app.core.decision_engine.wheel_v2.manual_plan import build_manual_plan
from app.core.decision_engine.wheel_v2.ownability import evaluate_ownability
from app.core.decision_engine.wheel_v2.phases import WheelPhase, phase_label
from app.core.decision_engine.wheel_v2.shares_v2 import build_shares_plan_v2
from app.core.decision_engine.wheel_v2.slack_payload import action_label, to_slack_ready_payload


def _g(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resolve_profile(
    profile: Optional[Union[str, StrategyProfile, Mapping[str, Any]]],
) -> Optional[StrategyProfile]:
    if profile is None:
        try:
            return get_profile("balanced")
        except Exception:
            return None
    if isinstance(profile, StrategyProfile):
        return profile
    if isinstance(profile, str):
        try:
            return get_profile(profile)
        except Exception:
            return None
    if isinstance(profile, Mapping):
        name = str(profile.get("name") or "balanced")
        try:
            return get_profile(name)
        except Exception:
            return None
    return None


def _finalize(
    *,
    symbol: str,
    phase: WheelPhase,
    action: str,
    strategy: Optional[str],
    ownability: Dict[str, Any],
    profile_name: str,
    reason_codes: List[str],
    manual_plan: ManualPlan,
    arbitration: Optional[Dict[str, Any]] = None,
    management: Optional[Dict[str, Any]] = None,
    assignment: Optional[Dict[str, Any]] = None,
    shares_plan: Optional[Dict[str, Any]] = None,
) -> WheelDecisionV2:
    draft = WheelDecisionV2(
        symbol=symbol,
        phase=phase.value,
        phase_label=phase_label(phase),
        action=action,
        action_label=action_label(action),
        strategy=strategy,
        ownability=ownability,
        arbitration=arbitration,
        manual_plan=manual_plan.to_dict(),
        management=management,
        assignment=assignment,
        shares_plan=shares_plan,
        reason_codes=list(reason_codes),
        profile=str(profile_name),
        manual_only=True,
        trade_execution=False,
    )
    return WheelDecisionV2(
        symbol=draft.symbol,
        phase=draft.phase,
        phase_label=draft.phase_label,
        action=draft.action,
        action_label=draft.action_label,
        strategy=draft.strategy,
        ownability=draft.ownability,
        arbitration=draft.arbitration,
        manual_plan=draft.manual_plan,
        management=draft.management,
        assignment=draft.assignment,
        shares_plan=draft.shares_plan,
        slack_payload=to_slack_ready_payload(draft),
        reason_codes=draft.reason_codes,
        profile=draft.profile,
        manual_only=True,
        trade_execution=False,
    )


def evaluate_wheel_v2(
    *,
    symbol: str,
    context: Optional[Mapping[str, Any]] = None,
    open_position: Optional[Any] = None,
    portfolio: Optional[Mapping[str, Any]] = None,
    profile: Optional[Union[str, StrategyProfile, Mapping[str, Any]]] = None,
    csp_eval: Optional[Any] = None,
    shares_eval: Optional[Any] = None,
    shares_summary: Optional[Any] = None,
    technicals: Optional[Dict[str, Any]] = None,
    wheel_state: Optional[str] = None,
) -> WheelDecisionV2:
    """
    Evaluate Wheel V2 for a symbol.

    Given symbol context + optional open position + portfolio + profile →
    WheelDecisionV2 with phase, action, arbitration, manual_plan, slack_payload.

    Pure/testable with fixtures; no live ORATS. Always manual_only / trade_execution=false.
    Stay in Cash remains a valid outcome.
    """
    sym = (symbol or "").strip().upper()
    ctx = dict(context or {})
    prof = _resolve_profile(profile)
    profile_name = prof.name if prof else (profile if isinstance(profile, str) else "balanced")

    own_inp = {
        "symbol": sym,
        "market_regime": ctx.get("market_regime") or ctx.get("regime"),
        "price": ctx.get("price") or (technicals or {}).get("spot"),
        "earnings_days": ctx.get("earnings_days"),
        "stage1_status": ctx.get("stage1_status"),
        "contract": ctx.get("contract"),
    }
    blackout = int(getattr(prof, "earnings_blackout_days", 7) if prof else 7)
    own = evaluate_ownability(
        own_inp,
        stage1_status=ctx.get("stage1_status"),
        quality_ok=ctx.get("quality_ok"),
        liquidity_ok=ctx.get("liquidity_ok"),
        earnings_blackout_days=blackout,
    )

    state = (wheel_state or ctx.get("wheel_state") or "").upper()
    strategy_hint = (_g(open_position, "strategy") or ctx.get("strategy") or "").upper()
    reason_codes: List[str] = list(own.reason_codes)

    # --- Open option management path ---
    if open_position is not None and strategy_hint in ("CSP", "CC", "COVERED_CALL"):
        management_out = manage_open_option(
            open_position,
            prof,
            spot=ctx.get("price") or (technicals or {}).get("spot"),
            mark_proxy=ctx.get("mark_proxy"),
        )
        mg_action = management_out["action"]
        phase = WheelPhase.CSP_MANAGE if strategy_hint == "CSP" else WheelPhase.CC_MANAGE
        strategy = "CSP" if strategy_hint == "CSP" else "CC"
        action = mg_action
        assignment_out = None

        assign_risk = (management_out.get("assignment_risk") or {}).get("active")
        if assign_risk or ctx.get("will_assign"):
            shares_held = int(ctx.get("shares_held") or _g(open_position, "shares_held") or 0)
            contracts = int(_g(open_position, "contracts") or 1)
            assignment_out = assignment_advisory(
                shares_held=shares_held,
                contracts=contracts,
                will_assign=True,
                ownability=own,
                strategy=strategy_hint,
            )
            phase = WheelPhase.ASSIGNMENT
            action = assignment_out["action"]
            reason_codes = list(assignment_out.get("reason_codes") or reason_codes)

        plan = build_manual_plan(
            strategy=strategy,
            action=action,
            strike=_g(open_position, "strike"),
            expiry=_g(open_position, "expiration") or _g(open_position, "expiry"),
            premium=_g(open_position, "open_credit") or _g(open_position, "credit_expected"),
            contracts=_g(open_position, "contracts"),
            earnings_days=ctx.get("earnings_days"),
            profile=prof,
            assignment_plan=(assignment_out or {}).get("next_phase") if assignment_out else None,
            sources=["wheel_v2", "management", "profit_management"],
            summary_label=f"{action} {strategy} {sym}",
        )
        return _finalize(
            symbol=sym,
            phase=phase,
            action=action,
            strategy=strategy,
            ownability=own.to_dict(),
            profile_name=str(profile_name),
            reason_codes=reason_codes,
            manual_plan=plan,
            management=management_out,
            assignment=assignment_out,
        )

    # --- Assigned / shares held → CC entry or exit ---
    shares_held = int(ctx.get("shares_held") or 0)
    if state == "ASSIGNED" or shares_held >= 100:
        if not own.ownable:
            phase = WheelPhase.EXIT
            action = "EXIT_SHARES"
            strategy = "SHARES"
        else:
            phase = WheelPhase.CC_ENTRY
            action = "OPEN_CC"
            strategy = "CC"
        assignment_out = assignment_advisory(
            shares_held=shares_held,
            contracts=1,
            will_assign=False,
            ownability=own,
            strategy="CSP",
        )
        plan = build_manual_plan(
            strategy=strategy,
            action=action,
            contract=ctx.get("contract") if isinstance(ctx.get("contract"), Mapping) else None,
            earnings_days=ctx.get("earnings_days"),
            profile=prof,
            shares=shares_held,
            assignment_plan=assignment_out.get("next_phase"),
            sources=["wheel_v2", "assignment"],
            summary_label=f"{action} {sym}",
        )
        return _finalize(
            symbol=sym,
            phase=phase,
            action=action,
            strategy=strategy,
            ownability=own.to_dict(),
            profile_name=str(profile_name),
            reason_codes=reason_codes,
            manual_plan=plan,
            assignment=assignment_out,
        )

    # --- Entry path: arbitration CSP vs shares ---
    csp_e = csp_eval if csp_eval is not None else ctx.get("csp_eval")
    shares_e = shares_eval if shares_eval is not None else ctx.get("shares_eval")
    shares_plan_out: Optional[Dict[str, Any]] = None

    if technicals is not None or shares_summary is not None or ctx.get("build_shares"):
        try:
            summary_obj = shares_summary or type(
                "S",
                (),
                {"stage1_status": ctx.get("stage1_status"), "price": ctx.get("price")},
            )()
            shares_plan_out = build_shares_plan_v2(
                summary_obj,
                technicals
                or {
                    "spot": ctx.get("price"),
                    "regime": ctx.get("market_regime"),
                    "support_level": ctx.get("support_level"),
                    "atr": ctx.get("atr"),
                    "rsi": ctx.get("rsi"),
                },
                exit_plan=ctx.get("exit_plan") or {},
                hold_time_estimate=ctx.get("hold_time_estimate"),
                symbol=sym,
                mtf_levels=ctx.get("mtf_levels"),
                as_of_inputs=ctx.get("as_of_inputs"),
                symbol_eligibility=ctx.get("symbol_eligibility") or {},
                account_summary=portfolio if isinstance(portfolio, dict) else None,
            )
            if shares_e is None:
                shares_e = {
                    "eligible": shares_plan_out.get("eligible"),
                    "score": 50.0 if shares_plan_out.get("eligible") else 0.0,
                    "decision_status": "ACTIONABLE" if shares_plan_out.get("eligible") else "BLOCKED",
                    "eligibility": shares_plan_out.get("eligible"),
                    "capital_required": (shares_plan_out.get("sizing") or {}).get("suggested_cost") or 0.0,
                    "sizing": shares_plan_out.get("sizing"),
                }
        except Exception:
            shares_plan_out = None

    arb = arbitrate_csp_vs_shares(csp_e, shares_e, portfolio, prof, ownable=own.ownable)
    arbitration_out = arb.to_dict()
    reason_codes = list(arb.reason_codes) + reason_codes

    if arb.winner == "CSP":
        phase = WheelPhase.CSP_ENTRY
        action = "OPEN_CSP"
        strategy = "CSP"
        contract = ctx.get("contract") if isinstance(ctx.get("contract"), Mapping) else None
        if isinstance(csp_e, Mapping) and csp_e.get("selected_contract"):
            contract = csp_e.get("selected_contract")
        plan = build_manual_plan(
            strategy="CSP",
            action=action,
            contract=contract,
            earnings_days=ctx.get("earnings_days"),
            profile=prof,
            assignment_plan="CC_ENTRY if assigned and ownable else EXIT",
            contracts=_g(csp_e, "contracts")
            if csp_e
            else ((contract or {}).get("contracts") if contract else 1),
            sources=["wheel_v2", "arbitration", "csp"],
            summary_label=f"Open CSP · {sym}",
        )
    elif arb.winner == "SHARES":
        phase = WheelPhase.SHARES_ENTRY
        action = "OPEN_SHARES"
        strategy = "SHARES"
        tranches = None
        thesis_plan = "Monitor stop / support"
        if shares_plan_out:
            tranches = (shares_plan_out.get("staged_entry") or {}).get("tranches")
            if (shares_plan_out.get("thesis_failure") or {}).get("active"):
                thesis_plan = "Exit if stop or support breaks"
                phase = WheelPhase.SHARES_MANAGE
                action = "EXIT_SHARES"
        plan = build_manual_plan(
            strategy="SHARES",
            action=action,
            shares=((shares_plan_out or {}).get("sizing") or {}).get("suggested_shares")
            if shares_plan_out
            else None,
            earnings_days=ctx.get("earnings_days"),
            profile=prof,
            staged_tranches=tranches,
            thesis_failure_plan=thesis_plan,
            sources=["wheel_v2", "arbitration", "shares_v2"],
            summary_label=f"Open shares · {sym}",
        )
    else:
        phase = WheelPhase.STAY_IN_CASH
        action = "STAY_IN_CASH"
        strategy = "CASH"
        plan = build_manual_plan(
            strategy="CASH",
            action=action,
            profile=prof,
            sources=["wheel_v2", "arbitration"],
            summary_label=f"Stay in cash · {sym}",
        )

    return _finalize(
        symbol=sym,
        phase=phase,
        action=action,
        strategy=strategy,
        ownability=own.to_dict(),
        profile_name=str(profile_name),
        reason_codes=reason_codes,
        manual_plan=plan,
        arbitration=arbitration_out,
        shares_plan=shares_plan_out,
    )
