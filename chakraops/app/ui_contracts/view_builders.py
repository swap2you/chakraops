# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""View builders: pure functions that build UI view models from persistence/domain (Phase 6.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.exit_plan import (
    DEFAULT_PROFIT_TARGET_PCT,
    exit_plan_from_dict,
    exit_plan_to_dict,
    get_default_exit_plan,
)
from app.ui_contracts.view_models import (
    AlertsView,
    DailyOverviewView,
    PerformanceSummaryView,
    PositionTimelineView,
    PositionView,
    TradePlanView,
)


def _credit_and_exit_plan(position: Any) -> Tuple[float, Any]:
    """(entry_credit or premium_collected, exit_plan or default)."""
    credit = getattr(position, "entry_credit", None) or getattr(
        position, "premium_collected", 0.0
    )
    credit = float(credit)
    ep = getattr(position, "exit_plan", None)
    strategy = getattr(position, "position_type", "CSP") or "CSP"
    if ep is None:
        ep = get_default_exit_plan(strategy)
    return credit, ep


def _compute_profit_target_premiums(credit: float, profit_target_pct: float) -> Dict[str, float]:
    """VIEW-only: t1/t2/t3 option premium levels to close at. Not used by StopEngine."""
    # t1 = profit_target_pct (default 60%)
    t1_pct = profit_target_pct
    t1 = credit * (1.0 - t1_pct)
    # t2 = min(0.80, profit_target_pct + 0.10)
    t2_pct = min(0.80, profit_target_pct + 0.10)
    t2 = credit * (1.0 - t2_pct)
    # t3 = 0.85 hard cap
    t3 = credit * (1.0 - 0.85)
    return {"t1": round(t1, 4), "t2": round(t2, 4), "t3": round(t3, 4)}


def _dte_from_expiry(expiry: Optional[str], now_date: Optional[str] = None) -> Optional[int]:
    if not expiry:
        return None
    try:
        from datetime import datetime as dt
        d1 = dt.strptime(expiry[:10], "%Y-%m-%d").date()
        if now_date:
            d2 = dt.strptime(now_date[:10], "%Y-%m-%d").date()
        else:
            d2 = datetime.now(timezone.utc).date()
        return (d1 - d2).days
    except (ValueError, TypeError, IndexError):
        return None


def build_position_view(
    position: Any,
    events: List[Dict[str, Any]],
    now_date: Optional[str] = None,
) -> PositionView:
    """Build PositionView from position and events. Deterministic; VIEW-only derived fields."""
    if now_date is None:
        now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    credit, exit_plan = _credit_and_exit_plan(position)
    pct = getattr(exit_plan, "profit_target_pct", None) or DEFAULT_PROFIT_TARGET_PCT
    profit_targets = _compute_profit_target_premiums(credit, float(pct))
    max_loss_mult = getattr(exit_plan, "max_loss_multiplier", 2.0)
    max_loss_estimate = credit * float(max_loss_mult) if max_loss_mult else None
    dte = _dte_from_expiry(getattr(position, "expiry", None), now_date)
    time_stop_days = getattr(exit_plan, "time_stop_days", None) or 14

    attention_reasons: List[str] = []
    for e in events:
        et = e.get("event_type") or ""
        if et == "TARGET_1_HIT":
            attention_reasons.append("TARGET_1_HIT")
        elif et == "STOP_TRIGGERED":
            attention_reasons.append("STOP_TRIGGERED")
    lifecycle = getattr(position, "lifecycle_state", None) or getattr(position, "state", "OPEN")
    if lifecycle in ("OPEN", "PARTIALLY_CLOSED") and dte is not None and time_stop_days is not None:
        if dte <= time_stop_days:
            attention_reasons.append("TIME_STOP_NEAR")
    needs_attention = len(attention_reasons) > 0

    strike_val = getattr(position, "strike", None)
    if isinstance(strike_val, (list, tuple)):
        strike_val = tuple(strike_val)
    elif strike_val is not None:
        strike_val = float(strike_val)

    return PositionView(
        position_id=getattr(position, "id", ""),
        symbol=getattr(position, "symbol", ""),
        strategy_type=getattr(position, "position_type", "CSP") or "CSP",
        lifecycle_state=lifecycle,
        opened=(getattr(position, "open_date", None) or (position.entry_date[:10] if getattr(position, "entry_date", None) else now_date)),
        expiry=getattr(position, "expiry", None),
        strike=strike_val,
        contracts=int(getattr(position, "contracts", 0)),
        entry_credit=credit,
        last_mark=None,
        dte=dte,
        unrealized_pnl=None,
        realized_pnl=float(getattr(position, "realized_pnl", 0) or 0),
        max_loss_estimate=max_loss_estimate,
        profit_targets=profit_targets,
        notes=str(getattr(position, "notes", "") or ""),
        needs_attention=needs_attention,
        attention_reasons=list(dict.fromkeys(attention_reasons)),
    )


def build_position_timeline_view(
    position_id: str,
    symbol: str,
    events: List[Dict[str, Any]],
) -> PositionTimelineView:
    """Build PositionTimelineView from events."""
    milestones: Dict[str, Optional[str]] = {
        "first_opened_at": None,
        "last_event_at": None,
        "last_event_type": None,
        "target_1_hit_at": None,
        "stop_triggered_at": None,
        "assigned_at": None,
        "closed_at": None,
    }
    if not events:
        return PositionTimelineView(position_id=position_id, symbol=symbol, events=[], milestones=milestones)
    milestones["first_opened_at"] = events[0].get("event_time")
    milestones["last_event_at"] = events[-1].get("event_time")
    milestones["last_event_type"] = events[-1].get("event_type")
    for e in events:
        et = e.get("event_type") or ""
        t = e.get("event_time")
        if et == "OPENED":
            if milestones["first_opened_at"] is None:
                milestones["first_opened_at"] = t
        elif et == "TARGET_1_HIT":
            milestones["target_1_hit_at"] = t
        elif et == "STOP_TRIGGERED":
            milestones["stop_triggered_at"] = t
        elif et == "ASSIGNED":
            milestones["assigned_at"] = t
        elif et == "CLOSED":
            milestones["closed_at"] = t
    return PositionTimelineView(
        position_id=position_id,
        symbol=symbol,
        events=events,
        milestones=milestones,
    )


def build_trade_plan_view(
    decision_ts: str,
    trade_proposal_row_or_dict: Dict[str, Any],
    maybe_position: Optional[Any] = None,
) -> TradePlanView:
    """Build TradePlanView from proposal (and optional position for exit_plan)."""
    prop = trade_proposal_row_or_dict if isinstance(trade_proposal_row_or_dict, dict) else {}
    proposal = prop.get("proposal_json")
    if isinstance(proposal, str):
        import json
        try:
            proposal = json.loads(proposal)
        except (TypeError, ValueError):
            proposal = {}
    if proposal is None:
        proposal = prop
    symbol = proposal.get("symbol") or prop.get("symbol", "")
    strategy_type = proposal.get("strategy_type") or prop.get("strategy_type", "CSP")
    credit = float(proposal.get("credit_estimate", 0) or proposal.get("credit_estimate", 0) or 0)
    exit_plan_dict = None
    if maybe_position and getattr(maybe_position, "exit_plan", None):
        exit_plan_dict = exit_plan_to_dict(maybe_position.exit_plan)
    if not exit_plan_dict:
        ep = get_default_exit_plan(strategy_type)
        exit_plan_dict = exit_plan_to_dict(ep)
    pct = (exit_plan_dict or {}).get("profit_target_pct", DEFAULT_PROFIT_TARGET_PCT)
    computed_targets = _compute_profit_target_premiums(credit, float(pct))

    blockers: List[str] = []
    if prop.get("rejection_reason"):
        blockers.append(prop["rejection_reason"])
    if prop.get("execution_status") == "BLOCKED":
        blockers.append("BLOCKED")
    if prop.get("rejected"):
        blockers.append(prop.get("rejection_reason") or "REJECTED")

    return TradePlanView(
        decision_ts=decision_ts,
        symbol=symbol,
        strategy_type=strategy_type,
        proposal=dict(proposal or {}),
        execution_status=str(prop.get("execution_status", "BLOCKED")),
        user_acknowledged=bool(prop.get("user_acknowledged", False)),
        execution_notes=str(prop.get("execution_notes") or ""),
        exit_plan=dict(exit_plan_dict or {}),
        computed_targets=computed_targets,
        blockers=blockers,
    )


def build_daily_overview_view(
    cycle: Optional[Dict[str, Any]],
    trust_report: Optional[Dict[str, Any]],
    decision_meta: Optional[Dict[str, Any]],
    freeze_state: Optional[Dict[str, Any]],
) -> DailyOverviewView:
    """Build DailyOverviewView from cycle, trust report, decision meta, freeze state. Robust if any is missing."""
    report = trust_report or {}
    meta = decision_meta or {}
    date_str = report.get("date") or report.get("cycle_id")
    if not date_str and cycle:
        date_str = cycle.get("cycle_id") or ""
    if not date_str and meta.get("decision_ts"):
        date_str = str(meta["decision_ts"])[:10]
    date_str = date_str or ""
    run_mode = report.get("run_mode") or (freeze_state or {}).get("run_mode", "DRY_RUN")
    config_frozen = report.get("config_frozen")
    if config_frozen is None and freeze_state:
        config_frozen = True  # best-effort
    if config_frozen is None:
        config_frozen = False
    freeze_keys = report.get("freeze_violation_changed_keys") or []

    regime = meta.get("regime") or report.get("regime")
    regime_reason = meta.get("regime_reason") or report.get("regime_reason")
    stats = meta.get("stats") or {}
    symbols_evaluated = int(report.get("trades_considered", 0) or stats.get("symbols_evaluated", 0) or stats.get("total_candidates", 0))
    selected_signals = int(meta.get("selected_signals_count", 0) or len(meta.get("selected_signals", [])) or 0)
    trades_ready = int(report.get("trades_ready", 0))
    no_trade = trades_ready == 0
    why_summary = str(report.get("summary", "") or meta.get("why_no_trade", {}).get("summary", "") or "")
    top_blockers = list(report.get("top_blocking_reasons") or [])
    risk_posture = str(meta.get("metadata", {}).get("risk_posture", "") or report.get("risk_posture", "CONSERVATIVE") or "CONSERVATIVE")
    links = {}
    if meta.get("decision_ts"):
        links["latest_decision_ts"] = meta["decision_ts"]

    return DailyOverviewView(
        date=date_str,
        run_mode=run_mode,
        config_frozen=bool(config_frozen),
        freeze_violation_changed_keys=freeze_keys,
        regime=regime,
        regime_reason=regime_reason,
        symbols_evaluated=symbols_evaluated,
        selected_signals=selected_signals,
        trades_ready=trades_ready,
        no_trade=no_trade,
        why_summary=why_summary,
        top_blockers=top_blockers,
        risk_posture=risk_posture,
        links=links,
    )


def build_performance_summary_view(as_of: Optional[str] = None) -> PerformanceSummaryView:
    """Build PerformanceSummaryView from ledger helpers. Deterministic."""
    from app.core.persistence import (
        get_capital_deployed_today,
        get_mtd_realized_pnl,
        compute_monthly_summary,
        get_monthly_summaries,
    )
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()
    mtd = get_mtd_realized_pnl()
    deployed = get_capital_deployed_today()
    now = datetime.now(timezone.utc)
    monthly = compute_monthly_summary(now.year, now.month)
    monthly_dict = {
        "year": monthly.year,
        "month": monthly.month,
        "total_credit_collected": monthly.total_credit_collected,
        "realized_pnl": monthly.realized_pnl,
        "unrealized_pnl": monthly.unrealized_pnl,
        "win_rate": monthly.win_rate,
        "avg_days_in_trade": monthly.avg_days_in_trade,
        "max_drawdown": monthly.max_drawdown,
    }
    last_3 = get_monthly_summaries(last_n=3)
    return PerformanceSummaryView(
        as_of=as_of,
        mtd_realized_pnl=mtd,
        capital_deployed_today=deployed,
        monthly=monthly_dict,
        last_3_months=last_3,
    )


def build_alerts_view(
    as_of: Optional[str],
    recent_events: List[Dict[str, Any]],
    daily_overview: Optional[DailyOverviewView],
) -> AlertsView:
    """Build AlertsView from recent position events and daily overview."""
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()
    items: List[Dict[str, Any]] = []
    seen_positions: set = set()
    for e in recent_events:
        et = e.get("event_type") or ""
        pid = e.get("position_id")
        if et == "TARGET_1_HIT":
            items.append({
                "level": "info",
                "code": "PROFIT_TARGET_HIT",
                "message": "Profit target hit",
                "symbol": (e.get("metadata") or {}).get("symbol", ""),
                "position_id": pid,
                "decision_ts": None,
            })
            if pid:
                seen_positions.add(pid)
        elif et == "STOP_TRIGGERED":
            items.append({
                "level": "warning",
                "code": "STOP_TRIGGERED",
                "message": "Stop triggered",
                "symbol": (e.get("metadata") or {}).get("symbol", ""),
                "position_id": pid,
                "decision_ts": None,
            })
            if pid:
                seen_positions.add(pid)

    if daily_overview:
        if daily_overview.freeze_violation_changed_keys:
            items.append({
                "level": "error",
                "code": "FREEZE_VIOLATION",
                "message": f"Config changed: {', '.join(daily_overview.freeze_violation_changed_keys)}",
                "symbol": "",
                "position_id": None,
                "decision_ts": daily_overview.links.get("latest_decision_ts"),
            })
        if daily_overview.no_trade and daily_overview.top_blockers:
            top = daily_overview.top_blockers[0] if daily_overview.top_blockers else {}
            code = top.get("code", "NO_TRADE")
            items.append({
                "level": "info",
                "code": "NO_TRADE",
                "message": f"No trade; top blocker: {code}",
                "symbol": "",
                "position_id": None,
                "decision_ts": daily_overview.links.get("latest_decision_ts"),
            })

    return AlertsView(as_of=as_of, items=items)
