# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Phase 6.5: UI data contracts and read-model views."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.exit_plan import get_default_exit_plan
from app.ui_contracts.view_models import (
    AlertsView,
    DailyOverviewView,
    PositionView,
    TradePlanView,
)
from app.ui_contracts.view_builders import (
    build_alerts_view,
    build_daily_overview_view,
    build_position_view,
    build_trade_plan_view,
    _compute_profit_target_premiums,
)


def test_position_view_builds_targets_deterministically_from_exit_plan_defaults():
    """PositionView profit_targets are derived from ExitPlan defaults (VIEW-only)."""
    credit = 300.0
    pct = 0.60  # default
    targets = _compute_profit_target_premiums(credit, pct)
    assert "t1" in targets and "t2" in targets and "t3" in targets
    # t1 = credit * (1 - 0.60) = 120
    assert abs(targets["t1"] - 120.0) < 0.01
    # t2 = credit * (1 - min(0.80, 0.70)) = credit * 0.30 = 90
    assert abs(targets["t2"] - 90.0) < 0.01
    # t3 = credit * 0.15 = 45
    assert abs(targets["t3"] - 45.0) < 0.01
    # Same inputs -> same outputs
    targets2 = _compute_profit_target_premiums(credit, pct)
    assert targets == targets2


def test_needs_attention_triggers_on_target_1_hit_and_stop_triggered():
    """needs_attention is True when events include TARGET_1_HIT or STOP_TRIGGERED."""
    class FakePosition:
        id = "pos-1"
        symbol = "SPY"
        position_type = "CSP"
        strike = 450.0
        expiry = "2026-06-20"
        contracts = 1
        premium_collected = 250.0
        entry_credit = 250.0
        entry_date = "2026-02-01T12:00:00"
        open_date = "2026-02-01"
        realized_pnl = 0.0
        lifecycle_state = "OPEN"
        state = "OPEN"
        notes = None
        exit_plan = get_default_exit_plan("CSP")

    events_target = [{"event_type": "OPENED", "event_time": "2026-02-01T12:00:00", "metadata": {}},
                     {"event_type": "TARGET_1_HIT", "event_time": "2026-02-10T10:00:00", "metadata": {}}]
    pv = build_position_view(FakePosition(), events_target, now_date="2026-02-15")
    assert pv.needs_attention is True
    assert "TARGET_1_HIT" in pv.attention_reasons

    events_stop = [{"event_type": "OPENED", "event_time": "2026-02-01T12:00:00", "metadata": {}},
                   {"event_type": "STOP_TRIGGERED", "event_time": "2026-02-10T10:00:00", "metadata": {}}]
    pv2 = build_position_view(FakePosition(), events_stop, now_date="2026-02-15")
    assert pv2.needs_attention is True
    assert "STOP_TRIGGERED" in pv2.attention_reasons

    events_none = [{"event_type": "OPENED", "event_time": "2026-02-01T12:00:00", "metadata": {}}]
    pv3 = build_position_view(FakePosition(), events_none, now_date="2026-02-15")
    assert pv3.needs_attention is False


def test_daily_overview_view_builds_from_trust_report_only():
    """DailyOverviewView can build from trust report only (decision meta missing)."""
    trust_report = {
        "date": "2026-02-01",
        "run_mode": "DRY_RUN",
        "config_frozen": True,
        "freeze_violation_changed_keys": [],
        "trades_considered": 50,
        "trades_ready": 0,
        "summary": "No READY trade; capital protected.",
        "top_blocking_reasons": [{"code": "REGIME", "count": 1}],
    }
    daily = build_daily_overview_view(
        cycle=None,
        trust_report=trust_report,
        decision_meta=None,
        freeze_state=None,
    )
    assert daily.date == "2026-02-01"
    assert daily.run_mode == "DRY_RUN"
    assert daily.config_frozen is True
    assert daily.symbols_evaluated == 50
    assert daily.trades_ready == 0
    assert daily.no_trade is True
    assert daily.why_summary == "No READY trade; capital protected."
    assert len(daily.top_blockers) == 1
    assert daily.top_blockers[0]["code"] == "REGIME"
    out = daily.to_dict()
    assert "date" in out and out["date"] == "2026-02-01"
    back = DailyOverviewView.from_dict(out)
    assert back.date == daily.date and back.run_mode == daily.run_mode


def test_alerts_view_includes_freeze_violation_when_changed_keys_exist():
    """AlertsView includes FREEZE_VIOLATION when freeze_violation_changed_keys present."""
    daily_overview = DailyOverviewView(
        date="2026-02-01",
        run_mode="PAPER_LIVE",
        config_frozen=False,
        freeze_violation_changed_keys=["volatility.vol_target", "scoring.min_score"],
        regime=None,
        regime_reason=None,
        symbols_evaluated=0,
        selected_signals=0,
        trades_ready=0,
        no_trade=True,
        why_summary="",
        top_blockers=[],
        risk_posture="CONSERVATIVE",
        links={"latest_decision_ts": "2026-02-01T14:00:00"},
    )
    alerts = build_alerts_view("2026-02-01T15:00:00", [], daily_overview)
    codes = [item["code"] for item in alerts.items]
    assert "FREEZE_VIOLATION" in codes
    freeze_item = next(i for i in alerts.items if i["code"] == "FREEZE_VIOLATION")
    assert "volatility.vol_target" in freeze_item["message"] or "vol_target" in freeze_item["message"]


def test_performance_summary_view_uses_ledger_helpers():
    """PerformanceSummaryView uses get_capital_deployed_today and get_mtd_realized_pnl."""
    from app.ui_contracts.view_builders import build_performance_summary_view
    from app.core.persistence import (
        get_capital_deployed_today,
        get_mtd_realized_pnl,
        init_persistence_db,
    )
    init_persistence_db()
    view = build_performance_summary_view(as_of="2026-02-01T12:00:00")
    assert hasattr(view, "mtd_realized_pnl")
    assert hasattr(view, "capital_deployed_today")
    assert hasattr(view, "monthly")
    assert hasattr(view, "last_3_months")
    assert isinstance(view.mtd_realized_pnl, (int, float))
    assert isinstance(view.capital_deployed_today, (int, float))
    assert isinstance(view.monthly, dict)
    assert "realized_pnl" in view.monthly
    assert "total_credit_collected" in view.monthly
    assert isinstance(view.last_3_months, list)


def test_position_view_to_dict_and_from_dict():
    """PositionView is JSON-serializable and round-trips."""
    pv = PositionView(
        position_id="pos-1",
        symbol="SPY",
        strategy_type="CSP",
        lifecycle_state="OPEN",
        opened="2026-02-01",
        expiry="2026-06-20",
        strike=450.0,
        contracts=1,
        entry_credit=250.0,
        last_mark=None,
        dte=30,
        unrealized_pnl=None,
        realized_pnl=0.0,
        max_loss_estimate=500.0,
        profit_targets={"t1": 100.0, "t2": 75.0, "t3": 37.5},
        notes="test",
        needs_attention=False,
        attention_reasons=[],
    )
    d = pv.to_dict()
    assert d["position_id"] == "pos-1"
    assert d["symbol"] == "SPY"
    assert json.loads(json.dumps(d)) == d
    pv2 = PositionView.from_dict(d)
    assert pv2.position_id == pv.position_id
    assert pv2.profit_targets == pv.profit_targets


def test_trade_plan_view_from_dict():
    """TradePlanView.from_dict restores from dict."""
    d = {
        "decision_ts": "2026-02-01T14:00:00",
        "symbol": "AAPL",
        "strategy_type": "CSP",
        "proposal": {"credit_estimate": 200.0},
        "execution_status": "BLOCKED",
        "user_acknowledged": False,
        "execution_notes": "",
        "exit_plan": {"profit_target_pct": 0.60},
        "computed_targets": {"t1": 80.0, "t2": 60.0, "t3": 30.0},
        "blockers": ["REGIME"],
    }
    tv = TradePlanView.from_dict(d)
    assert tv.decision_ts == d["decision_ts"]
    assert tv.symbol == "AAPL"
    assert tv.execution_status == "BLOCKED"
    assert tv.blockers == ["REGIME"]
    assert tv.to_dict()["symbol"] == "AAPL"


def test_alerts_view_to_dict():
    """AlertsView is JSON-serializable."""
    av = AlertsView(as_of="2026-02-01", items=[{"level": "info", "code": "NO_TRADE", "message": "No trade", "symbol": "", "position_id": None, "decision_ts": None}])
    d = av.to_dict()
    assert d["as_of"] == "2026-02-01"
    assert len(d["items"]) == 1
    assert d["items"][0]["code"] == "NO_TRADE"
