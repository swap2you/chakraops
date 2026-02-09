# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2C: Tests for lifecycle engine — Target1, Target2, Stop, Regime abort, cooldown."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.core.positions.models import Position
from app.core.lifecycle.engine import evaluate_position_lifecycle
from app.core.lifecycle.models import LifecycleAction, LifecycleState, ExitReason
from app.core.alerts.alert_engine import (
    build_lifecycle_alerts_for_run,
    _lifecycle_fingerprint,
    _get_recent_sent_fingerprints,
)
from app.core.alerts.models import AlertType


def _make_position(symbol: str = "NVDA", status: str = "OPEN", position_id: str = "pos_1") -> Position:
    return Position(
        position_id=position_id,
        account_id="acc_1",
        symbol=symbol,
        strategy="CSP",
        contracts=2,
        strike=170.0,
        expiration="2026-02-20",
        credit_expected=4.20,
        status=status,
    )


def _make_run(symbols: list) -> MagicMock:
    run = MagicMock()
    run.run_id = "eval_1"
    run.symbols = symbols
    run.regime = "NORMAL"
    return run


class TestLifecycleEngineTarget1:
    """Target1 hit → SCALE_OUT directive."""

    def test_target1_hit_scale_out(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 112.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.SCALE_OUT
        assert events[0].reason == ExitReason.TARGET_1
        assert "EXIT 1 CONTRACT" in events[0].directive

    def test_target1_hit_partial_exit_no_scale_out(self):
        """Already PARTIAL_EXIT; target1 hit again — wait for target2 if set."""
        pos = _make_position("NVDA", "PARTIAL_EXIT")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 112.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 0  # PARTIAL_EXIT + target1 hit + target2 set → wait for target2

    def test_target1_hit_partial_exit_no_target2_exit_all(self):
        """PARTIAL_EXIT, target1 hit, no target2 → EXIT ALL."""
        pos = _make_position("NVDA", "PARTIAL_EXIT")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": None}
        run = _make_run([{"symbol": "NVDA", "price": 112.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.EXIT
        assert events[0].reason == ExitReason.TARGET_2
        assert "EXIT ALL REMAINING" in events[0].directive


class TestLifecycleEngineTarget2:
    """Target2 hit → full exit."""

    def test_target2_hit_exit_all(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 118.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.EXIT
        assert events[0].reason == ExitReason.TARGET_2
        assert "EXIT ALL REMAINING" in events[0].directive


class TestLifecycleEngineStopLoss:
    """Stop hit → EXIT IMMEDIATELY (STOP LOSS)."""

    def test_stop_hit_exit_immediately(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 92.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.EXIT
        assert events[0].reason == ExitReason.STOP_LOSS
        assert "EXIT IMMEDIATELY" in events[0].directive


class TestLifecycleEngineRegimeAbort:
    """Regime flips disallowed → ABORT."""

    def test_regime_blocked_abort(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "BLOCKED", "primary_reason": "Regime disallowed"}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 105.0, "verdict": "BLOCKED"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.ABORT
        assert events[0].reason == ExitReason.REGIME_BREAK
        assert "ABORT" in events[0].directive


class TestLifecycleEngineDataFailure:
    """Data health failure → HOLD — DATA UNRELIABLE."""

    def test_data_unreliable_hold(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "BLOCKED", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 105.0, "verdict": "DATA_INCOMPLETE_FATAL"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 1
        assert events[0].action == LifecycleAction.HOLD
        assert events[0].reason == ExitReason.DATA_FAILURE
        assert "DATA UNRELIABLE" in events[0].directive


class TestLifecycleEngineClosedSkipped:
    """CLOSED positions not evaluated."""

    def test_closed_position_no_events(self):
        pos = _make_position("NVDA", "CLOSED")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
        run = _make_run([{"symbol": "NVDA", "price": 118.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 0


class TestLifecycleEngineNoTargets:
    """No targets or stop → no evaluation."""

    def test_no_targets_no_events(self):
        pos = _make_position("NVDA", "OPEN")
        symbol_explain = {"symbol": "NVDA", "verdict": "HOLD", "primary_reason": ""}
        targets = {"stop": None, "target1": None, "target2": None}
        run = _make_run([{"symbol": "NVDA", "price": 105.0, "verdict": "HOLD"}])

        events = evaluate_position_lifecycle(pos, symbol_explain, targets, run, eval_run_id="eval_1")
        assert len(events) == 0


class TestLifecycleFingerprint:
    """Cooldown per (position_id, action_type)."""

    def test_fingerprint_deterministic(self):
        fp1 = _lifecycle_fingerprint("pos_1", "SCALE_OUT")
        fp2 = _lifecycle_fingerprint("pos_1", "SCALE_OUT")
        assert fp1 == fp2

    def test_fingerprint_differs_by_position(self):
        fp1 = _lifecycle_fingerprint("pos_1", "SCALE_OUT")
        fp2 = _lifecycle_fingerprint("pos_2", "SCALE_OUT")
        assert fp1 != fp2

    def test_fingerprint_differs_by_action(self):
        fp1 = _lifecycle_fingerprint("pos_1", "SCALE_OUT")
        fp2 = _lifecycle_fingerprint("pos_1", "EXIT")
        assert fp1 != fp2


class TestBuildLifecycleAlerts:
    """build_lifecycle_alerts_for_run produces alerts."""

    def test_target1_produces_scale_out_alert(self, tmp_path):
        pos = _make_position("NVDA", "OPEN", "pos_xyz")
        targets_path = tmp_path / "NVDA_targets.json"
        with open(targets_path, "w") as f:
            json.dump({"symbol": "NVDA", "stop": 95.0, "target1": 110.0, "target2": 115.0}, f)

        with patch("app.core.positions.store.list_positions", return_value=[pos]):
            with patch("app.core.symbols.targets.get_targets") as mock_get_targets:
                mock_get_targets.return_value = {"stop": 95.0, "target1": 110.0, "target2": 115.0}
                run = _make_run([{"symbol": "NVDA", "price": 112.0, "verdict": "HOLD"}])
                config = {"enabled_alert_types": ["POSITION_SCALE_OUT"], "lifecycle_cooldown_hours": 4}
                alerts = build_lifecycle_alerts_for_run(run, config)
                assert len(alerts) == 1
                assert alerts[0].alert_type == AlertType.POSITION_SCALE_OUT
                assert alerts[0].severity.value == "WARN"


class TestNoDuplicateAlerts:
    """Cooldown suppresses duplicate lifecycle alerts."""

    def test_cooldown_suppresses_same_position_action(self, tmp_path):
        alerts_log = tmp_path / "alerts_log.jsonl"
        alerts_log.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        fp = _lifecycle_fingerprint("pos_1", "SCALE_OUT")
        rec = {
            "fingerprint": fp,
            "created_at": now,
            "alert_type": "POSITION_SCALE_OUT",
            "severity": "WARN",
            "summary": "EXIT 1 CONTRACT",
            "action_hint": "EXIT 1 CONTRACT",
            "sent": True,
            "sent_at": now,
            "suppressed_reason": None,
        }
        with open(alerts_log, "w") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        with patch("app.core.alerts.alert_engine._alerts_log_path", return_value=alerts_log):
            recent = _get_recent_sent_fingerprints(4 * 3600)
            assert fp in recent
