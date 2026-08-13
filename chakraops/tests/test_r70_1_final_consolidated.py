# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70.1 final consolidated notification integrity repair tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.core.broker.models import BrokerBalances, BrokerSnapshot, EquityPosition, OptionPosition


@pytest.fixture(autouse=True)
def _clear_notification_idempotency(tmp_path, monkeypatch):
    from app.core.alerts import alert_engine as ae

    monkeypatch.setattr(ae, "_get_alerts_dir", lambda: tmp_path / "alerts")
    ae.clear_notification_idempotency_state()
    yield
    ae.clear_notification_idempotency_state()


def _fresh_snap(*, conflict_symbol: Optional[str] = None, age_minutes: float = 5.0, stale: bool = False) -> BrokerSnapshot:
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    equities = []
    if conflict_symbol:
        equities.append(EquityPosition(symbol=conflict_symbol, quantity=1.0, average_cost=10.0))
    return BrokerSnapshot(
        account_alias="acct_individual",
        fetched_at=fetched,
        balances=BrokerBalances(cash=1000.0, buying_power=1000.0, equity=1000.0),
        equity_positions=equities,
        option_positions=[],
        freshness="fresh",
        completeness="complete",
        stale=stale,
        source="robinhood_mcp",
    )


def _patch_broker(monkeypatch, snap: Optional[BrokerSnapshot]):
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {
            "status": "READ_ONLY_AVAILABLE" if snap is not None else "UNAUTHENTICATED",
            "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": snap is not None,
            "auth": {"authenticated": snap is not None},
        },
    )


def test_signal_without_broker_snapshot_not_clear(monkeypatch):
    from app.core.alerts.models import Alert, AlertType, Severity
    from app.core.alerts.slack_notifier import SlackNotifier
    from app.core.portfolio.capital_authority_r70 import robinhood_conflict_check_label

    _patch_broker(monkeypatch, None)
    label = robinhood_conflict_check_label("UNAVAILABLE")
    assert "CLEAR" not in label
    assert "NOT PERFORMED" in label

    captured: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.get_webhook_for_channel",
        lambda ch: "https://hooks.example/signals",
    )
    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.post_slack_webhook",
        lambda url, payload, **k: captured.append(payload) or True,
    )
    monkeypatch.setattr("app.core.alerts.slack_status.update_slack_status", lambda *a, **k: None)
    alert = Alert(
        alert_type=AlertType.SIGNAL,
        severity=Severity.INFO,
        reason_code="SET_CHANGE",
        summary="Signal",
        action_hint="Review",
        fingerprint="fp1",
        created_at=datetime.now(timezone.utc).isoformat(),
        meta={"broker_freshness": "UNAVAILABLE", "robinhood_conflict_label": label},
    )
    SlackNotifier({}).send(alert)
    text = captured[-1]["text"]
    assert "no conflicting Robinhood position" not in text
    assert "NOT PERFORMED" in text or "UNKNOWN" in text


def test_signal_stale_snapshot_unknown(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import get_broker_freshness_view, robinhood_conflict_check_label

    _patch_broker(monkeypatch, _fresh_snap(age_minutes=200))
    view = get_broker_freshness_view("acct_individual")
    assert view["state"] == "STALE"
    label = robinhood_conflict_check_label(view["state"])
    assert "UNKNOWN" in label and "stale" in label.lower()


def test_signal_fresh_no_conflict_clear(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import (
        get_broker_freshness_view,
        robinhood_conflict_check_label,
        symbol_has_broker_conflict,
    )

    _patch_broker(monkeypatch, _fresh_snap())
    view = get_broker_freshness_view("acct_individual")
    assert view["state"] == "FRESH"
    conflict = symbol_has_broker_conflict("AAPL", freshness=view)
    assert conflict is False
    assert "CLEAR" in robinhood_conflict_check_label(view["state"], conflict=conflict)


def test_signal_fresh_conflict(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import (
        get_broker_freshness_view,
        robinhood_conflict_check_label,
        symbol_has_broker_conflict,
    )

    _patch_broker(monkeypatch, _fresh_snap(conflict_symbol="AAPL"))
    view = get_broker_freshness_view("acct_individual")
    conflict = symbol_has_broker_conflict("AAPL", freshness=view)
    assert conflict is True
    assert "CONFLICT" in robinhood_conflict_check_label(view["state"], conflict=conflict)


def test_exit_abort_never_claims_live_from_journal(monkeypatch):
    from app.core.alerts.models import Alert, AlertType, Severity
    from app.core.alerts.slack_notifier import SlackNotifier

    _patch_broker(monkeypatch, None)
    captured: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.get_webhook_for_channel",
        lambda ch: "https://hooks.example/critical",
    )
    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.post_slack_webhook",
        lambda url, payload, **k: captured.append(payload) or True,
    )
    monkeypatch.setattr("app.core.alerts.slack_status.update_slack_status", lambda *a, **k: None)
    alert = Alert(
        alert_type=AlertType.POSITION_ABORT,
        severity=Severity.CRITICAL,
        reason_code="REGIME_ABORT",
        summary="Abort",
        action_hint="CLOSE",
        fingerprint="fp-abort",
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol="SPY",
        meta={
            "lifecycle_format": "directive",
            "live_confirmed": False,
            "broker_state": "manual journal — not a LIVE Robinhood open",
            "account_alias": "acct_individual",
            "broker_source": "manual_journal",
            "quantity": 1,
            "contract_key": "SPY_20260919_P_500",
            "eval_run_id": "eval_test_1",
        },
    )
    SlackNotifier({}).send(alert)
    body = captured[-1]["blocks"][0]["text"]["text"].lower()
    assert "not a live robinhood open" in body or "advisory" in captured[-1]["text"].lower()
    assert "live robinhood open" not in body or "not a live" in body


def test_daily_summary_contains_broker_state(monkeypatch):
    from app.core.alerts.eval_summary import build_eval_summary_payload

    _patch_broker(monkeypatch, _fresh_snap())
    monkeypatch.setattr(
        "app.api.data_health.get_orats_freshness_state",
        lambda: {"state": "OK", "as_of": "2026-08-13T16:00:00+00:00"},
    )
    run = MagicMock()
    run.run_id = "eval_20260813_test"
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:45:59.954155+00:00"
    run.total = 166
    run.eligible = 1
    run.symbols = []
    run.top_candidates = []
    payload = build_eval_summary_payload(run)
    assert payload["broker_state"] == "FRESH"
    assert payload["open_positions"] == "0"
    assert payload["account_alias"] == "acct_individual"
    assert payload["broker_as_of"]
    from app.core.alerts.slack_notifier import SlackNotifier

    text = SlackNotifier({})._format_eval_summary(payload)
    assert "broker=FRESH" in text
    assert "broker open=0" in text
    assert "MANUAL ONLY — NO ORDER SENT" in text


def test_daily_summary_exposes_stale_orats_actionability(monkeypatch):
    from app.core.alerts.eval_summary import build_eval_summary_payload
    from app.core.alerts.slack_notifier import SlackNotifier

    _patch_broker(monkeypatch, _fresh_snap(age_minutes=200))
    monkeypatch.setattr(
        "app.api.data_health.get_orats_freshness_state",
        lambda: {"state": "ERROR", "as_of": "2026-02-27T00:00:00+00:00"},
    )
    run = MagicMock()
    run.run_id = "eval_stale"
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 10
    run.eligible = 0
    run.symbols = []
    run.top_candidates = []
    payload = build_eval_summary_payload(run)
    assert payload["broker_state"] == "STALE"
    assert payload["orats_state"] == "ERROR"
    assert payload["actionability"] == "DATA NOT ACTIONABLE"
    text = SlackNotifier({})._format_eval_summary(payload)
    assert "DATA NOT ACTIONABLE" in text
    assert "broker open=UNKNOWN" in text


def test_freshness_agreement_guardrails_lenses_slack(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import get_broker_freshness_view, get_capital_snapshot
    from app.core.portfolio.live_position_lenses_r70 import build_live_position_lenses

    _patch_broker(monkeypatch, _fresh_snap(age_minutes=200))
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._manual_recovery_positions", lambda: [])
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._paper_open_positions", lambda: [])
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._historical_closed_count", lambda: 0)
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 0, "open_paper_count": 0},
    )
    view = get_broker_freshness_view("acct_individual")
    cap = get_capital_snapshot("acct_individual")
    lenses = build_live_position_lenses()
    assert view["state"] == cap["state"] == lenses["live_state"] == "STALE"
    assert view["sizing_blocked"] is True
    assert lenses["sizing_blocked"] is True
    assert cap["sizing_blocked"] is True


def test_sanitize_preserves_timestamp_and_run_id():
    from app.core.alerts.slack_dispatcher import sanitize_slack_payload, sanitize_slack_text

    ts = "2026-08-13T16:45:59.954155+00:00"
    run_id = "eval_20260813_164559_de5ba038"
    clean = sanitize_slack_text(f"{ts} · {run_id} · acct_individual · score=72.5 · DTE=37")
    assert ts in clean
    assert run_id in clean
    assert "acct_individual" in clean
    assert "72.5" in clean
    assert "37" in clean

    dirty = {
        "text": f"token=abc FAIL_FOO {ts}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"https://hooks.slack.com/services/T/B/x account_number=123456789 "
                        f"{run_id} C:\\Users\\x\\secret Traceback (most recent call last): boom"
                    ),
                },
            }
        ],
    }
    out = sanitize_slack_payload(dirty)
    blob = str(out)
    assert "hooks.slack.com" not in blob
    assert "FAIL_" not in blob
    assert "Traceback" not in blob
    assert "[path redacted]" in blob or "path redacted" in blob
    assert "token=[redacted]" in blob or "[redacted]" in blob
    assert "[acct redacted]" in blob or "account_number=[acct redacted]" in blob
    assert run_id in blob
    assert ".954155" in blob  # fractional seconds preserved
    assert ".[acct]" not in blob


def test_durable_idempotency_and_failed_retry(monkeypatch, tmp_path):
    from app.core.alerts.alert_engine import (
        _delivery_was_sent,
        clear_notification_idempotency_state,
        process_run_completed,
    )

    clear_notification_idempotency_state()
    sends = {"n": 0}

    def _send_summary(ch, payload):
        sends["n"] += 1
        if sends["n"] == 1:
            raise RuntimeError("boom")
        return True

    run = MagicMock()
    run.run_id = "dur-1"
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 1
    run.eligible = 0
    run.symbols = []
    run.top_candidates = []
    run.duration_seconds = 1.0
    run.primary_reason = None
    run.errors = []

    with patch("app.core.alerts.slack_notifier.SlackNotifier.send", return_value=False):
        with patch("app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary", side_effect=_send_summary):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    process_run_completed(run)
                    assert _delivery_was_sent("dur-1", "EVAL_SUMMARY") is False
                    process_run_completed(run)
                    assert _delivery_was_sent("dur-1", "EVAL_SUMMARY") is True
                    process_run_completed(run)
    assert sends["n"] == 2  # fail then success; third skipped


def test_retry_after_budget_not_violated():
    from app.core.alerts.slack_dispatcher import post_slack_webhook

    class _Resp:
        def __init__(self, code, headers=None, text=""):
            self.status_code = code
            self.headers = headers or {}
            self.text = text

    calls = {"n": 0}

    def _post(*a, **k):
        calls["n"] += 1
        return _Resp(429, {"Retry-After": "30"})

    with patch("app.core.alerts.slack_dispatcher._requests") as req:
        req.post.side_effect = _post
        with patch("app.core.alerts.slack_dispatcher._pace_channel", lambda *_a, **_k: None):
            with patch("app.core.alerts.slack_dispatcher.time.sleep") as sleep:
                ok = post_slack_webhook("https://hooks.example/x", {"text": "hi"}, channel_key="signals")
                assert ok is False
                sleep.assert_not_called()
        assert calls["n"] == 1


def test_permanent_4xx_not_retried():
    from app.core.alerts.slack_dispatcher import post_slack_webhook

    class _Resp:
        status_code = 400
        headers = {}
        text = "bad"

    calls = {"n": 0}

    def _post(*a, **k):
        calls["n"] += 1
        return _Resp()

    with patch("app.core.alerts.slack_dispatcher._requests") as req:
        req.post.side_effect = _post
        with patch("app.core.alerts.slack_dispatcher._pace_channel", lambda *_a, **_k: None):
            assert post_slack_webhook("https://hooks.example/x", {"text": "hi"}, channel_key="signals") is False
        assert calls["n"] == 1


def test_coordinator_run_id_correlation(monkeypatch):
    from app.core.eval import eval_coordinator as ec
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2

    written = {}

    class _Store:
        def set_latest(self, artifact):
            written["meta"] = dict(artifact.metadata)

    artifact = DecisionArtifactV2(
        metadata={"mode": "LIVE", "pipeline_timestamp": "t", "run_id": "old"},
        symbols=[],
        selected_candidates=[],
    )

    def _eval(symbols, mode="LIVE", coordinator_run_id=None, output_dir=None):
        evaluator = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        artifact.metadata = {
            "mode": mode,
            "pipeline_timestamp": "2026-08-13T16:45:59.954155+00:00",
            "run_id": coordinator_run_id or evaluator,
            "evaluator_run_id": evaluator,
            "coordinator_run_id": coordinator_run_id,
            "eligible_count": 0,
            "universe_size": 1,
            "evaluated_count_stage1": 1,
            "evaluated_count_stage2": 0,
        }
        written["meta"] = dict(artifact.metadata)
        return artifact

    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "eval_20260813_164559_de5ba038"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-13T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "eval_20260813_164559_de5ba038"
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr("app.core.eval.evaluation_service_v2.evaluate_universe", _eval)
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", lambda run: None)
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    monkeypatch.setattr("app.core.universe_v2.builder.build_universe_v2_snapshot", lambda: None)
    monkeypatch.setattr(
        "app.core.alerts.options_lifecycle_notifications.emit_options_lifecycle_notifications_from_run",
        lambda run: None,
    )
    monkeypatch.setattr("app.core.alerts.alert_engine.process_run_completed", lambda run: None)

    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="api")
    assert out.get("started") is True
    assert out.get("run_id") == "eval_20260813_164559_de5ba038"
    assert written["meta"]["run_id"] == "eval_20260813_164559_de5ba038"
    assert written["meta"]["coordinator_run_id"] == "eval_20260813_164559_de5ba038"
    assert written["meta"]["evaluator_run_id"] != written["meta"]["run_id"]


def test_slack_failure_does_not_corrupt_artifacts(monkeypatch, tmp_path):
    from app.core.alerts.alert_engine import process_run_completed
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH

    before = DECISION_STORE_PATH.read_bytes() if DECISION_STORE_PATH.exists() else b""
    run = MagicMock()
    run.run_id = "ok-fail-slack"
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 1
    run.eligible = 0
    run.symbols = []
    run.top_candidates = []
    run.duration_seconds = 1.0
    with patch("app.core.alerts.slack_notifier.SlackNotifier.send", side_effect=RuntimeError("x")):
        with patch("app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary", side_effect=RuntimeError("y")):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    process_run_completed(run)
    after = DECISION_STORE_PATH.read_bytes() if DECISION_STORE_PATH.exists() else b""
    assert after == before


def test_paper_failed_skip_send_nothing(monkeypatch):
    from app.core.alerts.alert_engine import process_run_completed
    from app.core.eval import eval_coordinator as ec

    calls: List[Any] = []
    monkeypatch.setattr("app.core.alerts.alert_engine.process_run_completed", lambda run: calls.append(run))
    artifact = SimpleNamespace(
        symbols=[],
        metadata={"universe_size": 0, "evaluated_count_stage1": 0, "eligible_count": 0, "market_phase": "OPEN"},
    )
    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "paper-1"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-13T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "paper-1"
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        lambda symbols, mode="LIVE", coordinator_run_id=None, output_dir=None: artifact,
    )
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", lambda run: None)
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    monkeypatch.setattr("app.core.universe_v2.builder.build_universe_v2_snapshot", lambda: None)
    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="PAPER", trigger="api", allow_when_closed=True)
    assert out.get("started") is True
    assert calls == []

    summary_calls: List[Any] = []
    failed = MagicMock()
    failed.run_id = "fail-x"
    failed.status = "FAILED"
    failed.symbols = []
    failed.top_candidates = []
    failed.completed_at = "t"
    failed.total = 0
    failed.eligible = 0
    with patch(
        "app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary",
        side_effect=lambda ch, payload: summary_calls.append(payload) or True,
    ):
        with patch("app.core.alerts.slack_notifier.SlackNotifier.send", return_value=False):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    process_run_completed(failed)
    assert summary_calls == []
