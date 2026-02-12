# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for exit rules engine: rule triggers with synthetic EOD snapshot and trade data."""

from __future__ import annotations

import pytest

from app.core.journal.models import Trade, Fill, FillAction
from app.core.journal.eod_snapshot import EODSnapshot
from app.core.journal.exit_rules import (
    evaluate_csp_rules,
    evaluate_cc_rules,
    evaluate_exit_rules,
    best_action_from_alerts,
    ExitRuleAlert,
)


# ---------------------------------------------------------------------------
# CSP: STOP_BREACH when close < EMA50 - 1.5*ATR14
# ---------------------------------------------------------------------------


def test_csp_stop_breach_triggered() -> None:
    """STOP_BREACH when close < EMA50 - 1.5*ATR14."""
    trade = Trade(
        trade_id="t1",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry="2026-03-21",
        strike=500.0,
        side="SELL",
        contracts=1,
        entry_mid_est=2.0,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    # Threshold = 105 - 1.5*2 = 102. Close 100 < 102 -> breach
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=103.0, atr14=2.0, rsi=45.0)
    alerts = evaluate_csp_rules(trade, snapshot)
    codes = [a.rule_code for a in alerts]
    assert "STOP_BREACH" in codes
    breach = next(a for a in alerts if a.rule_code == "STOP_BREACH")
    assert breach.severity == "critical"
    assert "100" in breach.message
    assert "102" in breach.message


def test_csp_stop_breach_not_triggered_when_above_threshold() -> None:
    """No STOP_BREACH when close >= EMA50 - 1.5*ATR14."""
    trade = Trade(
        trade_id="t2",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=103.0, ema50=105.0, ema20=103.0, atr14=2.0, rsi=50.0)
    alerts = evaluate_csp_rules(trade, snapshot)
    codes = [a.rule_code for a in alerts]
    assert "STOP_BREACH" not in codes


# ---------------------------------------------------------------------------
# CSP: RISK_ALERT when RSI < 35 and EMA20 < EMA50
# ---------------------------------------------------------------------------


def test_csp_risk_alert_triggered() -> None:
    """RISK_ALERT when RSI < 35 and trending down (EMA20 < EMA50)."""
    trade = Trade(
        trade_id="t3",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=102.0, atr14=2.0, rsi=32.0)
    alerts = evaluate_csp_rules(trade, snapshot)
    codes = [a.rule_code for a in alerts]
    assert "RISK_ALERT" in codes
    risk = next(a for a in alerts if a.rule_code == "RISK_ALERT")
    assert risk.severity == "warning"
    assert "RSI" in risk.message
    assert "downtrend" in risk.message.lower() or "EMA20" in risk.message


def test_csp_risk_alert_not_triggered_when_rsi_high() -> None:
    """No RISK_ALERT when RSI >= 35."""
    trade = Trade(
        trade_id="t4",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=102.0, atr14=2.0, rsi=40.0)
    alerts = evaluate_csp_rules(trade, snapshot)
    assert not any(a.rule_code == "RISK_ALERT" for a in alerts)


# ---------------------------------------------------------------------------
# CSP: PROFIT_T1 (manual check when 50% target level set)
# ---------------------------------------------------------------------------


def test_csp_profit_t1_manual_check_when_50_target() -> None:
    """PROFIT_T1 with 'manual check' when target_levels contains 0.5."""
    trade = Trade(
        trade_id="t5",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=2.0,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[0.5, 0.25],
        fills=[],
    )
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=103.0, atr14=2.0, rsi=50.0)
    alerts = evaluate_csp_rules(trade, snapshot)
    codes = [a.rule_code for a in alerts]
    assert "PROFIT_T1" in codes
    t1 = next(a for a in alerts if a.rule_code == "PROFIT_T1")
    assert t1.recommended_action == "manual check"


# ---------------------------------------------------------------------------
# CC: ROLL_ALERT when close > strike - 0.5*ATR14
# ---------------------------------------------------------------------------


def test_cc_roll_alert_triggered() -> None:
    """ROLL_ALERT when close > strike - 0.5*ATR14."""
    trade = Trade(
        trade_id="t6",
        symbol="SPY",
        strategy="CC",
        opened_at="2026-02-01T10:00:00Z",
        expiry="2026-03-21",
        strike=500.0,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    # strike - 0.5*ATR = 500 - 1 = 499. Close 501 > 499 -> roll alert
    snapshot = EODSnapshot(close=501.0, ema50=498.0, ema20=499.0, atr14=2.0, rsi=55.0)
    alerts = evaluate_cc_rules(trade, snapshot)
    assert len(alerts) >= 1
    assert alerts[0].rule_code == "ROLL_ALERT"
    assert alerts[0].severity == "warning"
    assert "501" in alerts[0].message
    assert "499" in alerts[0].message


def test_cc_roll_alert_not_triggered_when_below_threshold() -> None:
    """No ROLL_ALERT when close <= strike - 0.5*ATR14."""
    trade = Trade(
        trade_id="t7",
        symbol="SPY",
        strategy="CC",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=500.0,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=497.0, ema50=498.0, ema20=497.0, atr14=2.0, rsi=50.0)
    alerts = evaluate_cc_rules(trade, snapshot)
    assert not any(a.rule_code == "ROLL_ALERT" for a in alerts)


# ---------------------------------------------------------------------------
# Dispatcher and best_action
# ---------------------------------------------------------------------------


def test_evaluate_exit_rules_dispatches_csp() -> None:
    """evaluate_exit_rules returns CSP rules for strategy CSP."""
    trade = Trade(
        trade_id="t8",
        symbol="SPY",
        strategy="CSP",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=102.0, atr14=2.0, rsi=32.0)
    alerts = evaluate_exit_rules(trade, snapshot)
    assert any(a.rule_code == "STOP_BREACH" for a in alerts)
    assert any(a.rule_code == "RISK_ALERT" for a in alerts)


def test_evaluate_exit_rules_dispatches_cc() -> None:
    """evaluate_exit_rules returns CC rules for strategy CC."""
    trade = Trade(
        trade_id="t9",
        symbol="SPY",
        strategy="CC",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=500.0,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=501.0, ema50=498.0, ema20=499.0, atr14=2.0, rsi=55.0)
    alerts = evaluate_exit_rules(trade, snapshot)
    assert any(a.rule_code == "ROLL_ALERT" for a in alerts)


def test_evaluate_exit_rules_unknown_strategy_returns_empty() -> None:
    """evaluate_exit_rules returns [] for unknown strategy."""
    trade = Trade(
        trade_id="t10",
        symbol="SPY",
        strategy="OTHER",
        opened_at="2026-02-01T10:00:00Z",
        expiry=None,
        strike=None,
        side="SELL",
        contracts=1,
        entry_mid_est=None,
        run_id=None,
        notes=None,
        stop_level=None,
        target_levels=[],
        fills=[],
    )
    snapshot = EODSnapshot(close=100.0, ema50=105.0, ema20=103.0, atr14=2.0, rsi=30.0)
    alerts = evaluate_exit_rules(trade, snapshot)
    assert alerts == []


def test_best_action_from_alerts_prioritizes_critical() -> None:
    """best_action_from_alerts picks critical over warning over info."""
    alerts = [
        ExitRuleAlert("t1", "SPY", "PROFIT_T1", "info", "Take profit?", "manual check", {}),
        ExitRuleAlert("t1", "SPY", "STOP_BREACH", "critical", "Stop breach", "close", {}),
    ]
    best = best_action_from_alerts(alerts)
    assert best is not None
    assert best["severity"] == "critical"
    assert best["rule_code"] == "STOP_BREACH"
    assert best["action"] == "close"


def test_best_action_from_alerts_empty_returns_none() -> None:
    """best_action_from_alerts returns None for empty list."""
    assert best_action_from_alerts([]) is None
