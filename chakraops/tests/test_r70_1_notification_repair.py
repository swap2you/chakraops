# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70.1: Coordinator Slack notification repair — routing, payloads, idempotency."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_notification_idempotency():
    from app.core.alerts.alert_engine import clear_notification_idempotency_state

    clear_notification_idempotency_state()
    yield
    clear_notification_idempotency_state()


def _completed_run(run_id: str = "coord-live-1") -> MagicMock:
    run = MagicMock()
    run.run_id = run_id
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 10
    run.evaluated = 10
    run.eligible = 1
    run.holds = 0
    run.blocks = 0
    run.symbols = [{"symbol": "SPY", "verdict": "ELIGIBLE", "score": 72}]
    run.top_candidates = [
        {"symbol": "SPY", "score": 72, "candidate_trades": [{"strategy": "CSP"}]},
    ]
    run.duration_seconds = 8.0
    run.primary_reason = None
    run.errors = []
    return run


def test_coordinator_live_calls_process_run_completed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import eval_coordinator as ec
    from app.core.eval import evaluation_service_v2 as service

    artifact = SimpleNamespace(
        symbols=[SimpleNamespace(symbol="SPY", verdict="ELIGIBLE", primary_reason="x", score=72)],
        metadata={"universe_size": 1, "evaluated_count_stage1": 1, "eligible_count": 1, "market_phase": "OPEN"},
    )
    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "live-1"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-13T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "live-1"
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        lambda symbols, mode="LIVE", coordinator_run_id=None, output_dir=None: artifact,
    )
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", lambda run: None)
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    monkeypatch.setattr("app.core.universe_v2.builder.build_universe_v2_snapshot", lambda: None)
    monkeypatch.setattr(
        "app.core.alerts.options_lifecycle_notifications.emit_options_lifecycle_notifications_from_run",
        lambda run: None,
    )
    calls: List[Any] = []
    monkeypatch.setattr(
        "app.core.alerts.alert_engine.process_run_completed",
        lambda run: calls.append(run),
    )
    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="api")
    assert out.get("started") is True
    assert len(calls) == 1
    assert service._canonical_live_universe_write_is_authorized() is False


def test_coordinator_paper_does_not_call_process_run_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import eval_coordinator as ec

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
    calls: List[Any] = []
    monkeypatch.setattr(
        "app.core.alerts.alert_engine.process_run_completed",
        lambda run: calls.append(run),
    )
    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="PAPER", trigger="api", allow_when_closed=True)
    assert out.get("started") is True
    assert calls == []


def test_failed_evaluation_does_not_send_eval_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.alerts.alert_engine import process_run_completed

    run = _completed_run("fail-1")
    run.status = "FAILED"
    summary_calls: List[Any] = []
    with patch("app.core.alerts.slack_notifier.SlackNotifier.send", return_value=False):
        with patch(
            "app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary",
            side_effect=lambda ch, payload: summary_calls.append((ch, payload)) or True,
        ):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    process_run_completed(run)
    assert summary_calls == []


def test_slack_exception_does_not_corrupt_completed_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.alerts.alert_engine import process_run_completed

    run = _completed_run("ok-slack-fail")
    with patch(
        "app.core.alerts.slack_notifier.SlackNotifier.send",
        side_effect=RuntimeError("webhook boom"),
    ):
        with patch(
            "app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary",
            side_effect=RuntimeError("summary boom"),
        ):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    # Must not raise — evaluation already completed.
                    process_run_completed(run)


def test_duplicate_process_run_completed_is_idempotent() -> None:
    from app.core.alerts.alert_engine import process_run_completed

    run = _completed_run("dup-1")
    summary_calls: List[Any] = []
    with patch("app.core.alerts.slack_notifier.SlackNotifier.send", return_value=False):
        with patch(
            "app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary",
            side_effect=lambda ch, payload: summary_calls.append((ch, payload)) or True,
        ):
            with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
                with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                    process_run_completed(run)
                    process_run_completed(run)
    assert len(summary_calls) == 1


def test_options_lifecycle_hook_does_not_call_slack() -> None:
    """Lifecycle UI notifications must not duplicate SlackNotifier traffic."""
    import inspect

    from app.core.alerts import options_lifecycle_notifications as oln

    src = inspect.getsource(oln)
    assert "SlackNotifier" not in src
    assert "send_eval_summary" not in src
    assert "post_slack_webhook" not in src
    assert "send_slack_message" not in src


def test_channel_routing_and_mobile_text_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.alerts.models import Alert, AlertType, Severity
    from app.core.alerts.slack_notifier import SlackNotifier

    captured: List[Dict[str, Any]] = []

    def _fake_post(url, payload, channel_key="default", timeout_sec=10.0):
        # Never expose webhook URL in assertions beyond presence of scheme.
        assert url.startswith("https://hooks.example/")
        assert "hooks.slack.com" not in str(payload)
        assert "text" in payload
        assert "FAIL_" not in payload["text"]
        assert "WARN_" not in payload["text"]
        captured.append({"channel_key": channel_key, "payload": payload, "url_suffix": url.rsplit("/", 1)[-1]})
        return True

    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.get_webhook_for_channel",
        lambda ch: {
            "critical": "https://hooks.example/critical",
            "signals": "https://hooks.example/signals",
            "data_health": "https://hooks.example/data_health",
            "daily": "https://hooks.example/daily",
        }.get(ch),
    )
    monkeypatch.setattr("app.core.alerts.slack_dispatcher.post_slack_webhook", _fake_post)
    monkeypatch.setattr("app.core.alerts.slack_status.update_slack_status", lambda *a, **k: None)

    now = datetime.now(timezone.utc).isoformat()
    notifier = SlackNotifier({})
    cases = [
        (
            Alert(
                alert_type=AlertType.POSITION_ABORT,
                severity=Severity.CRITICAL,
                reason_code="REGIME_ABORT",
                summary="Abort required",
                action_hint="CLOSE",
                fingerprint="fp-abort",
                created_at=now,
                symbol="SPY",
                meta={"lifecycle_format": "directive", "quantity": 1, "contract_key": "SPY_20260919_P_500"},
            ),
            "critical",
            "ABORT",
        ),
        (
            Alert(
                alert_type=AlertType.SIGNAL,
                severity=Severity.INFO,
                reason_code="ELIGIBLE",
                summary="New CSP setup",
                action_hint="Review",
                fingerprint="fp-signal",
                created_at=now,
                symbol="AAPL",
                meta={"strategy": "CSP", "quantity": 1},
            ),
            "signals",
            "NEW SETUP",
        ),
        (
            Alert(
                alert_type=AlertType.DATA_HEALTH,
                severity=Severity.WARN,
                reason_code="ORATS_STALE",
                summary="ORATS freshness degraded",
                action_hint="Re-run when recovered",
                fingerprint="fp-health",
                created_at=now,
            ),
            "data_health",
            "BROKER/ORATS/SYSTEM ISSUE",
        ),
    ]
    for alert, channel, preview_prefix in cases:
        assert notifier._channel_for_alert(alert) == channel
        assert notifier.send(alert) is True
        last = captured[-1]
        assert last["channel_key"] == channel
        assert last["url_suffix"] == channel or last["url_suffix"] == "data_health"
        assert last["payload"]["text"].startswith(preview_prefix) or preview_prefix in last["payload"]["text"]
        assert "blocks" in last["payload"]
        assert "MANUAL ONLY — NO ORDER SENT" in last["payload"]["text"]
        assert "no conflicting Robinhood position" not in last["payload"]["text"]

    assert notifier.send_eval_summary(
        "daily",
        {
            "mode": "LIVE",
            "run_id": "r1",
            "timestamp": now,
            "total": 10,
            "eligible": 1,
            "a_tier": 0,
            "b_tier": 1,
            "blocked": 0,
            "alerts_sent": {"critical": 0, "signals": 1, "data_health": 0},
            "payload_type": "EVAL_SUMMARY",
        },
    )
    daily = captured[-1]
    assert daily["channel_key"] == "daily"
    assert "LIVE eval complete" in daily["payload"]["text"]
    assert "hooks.slack.com" not in daily["payload"]["text"]


def test_expanded_position_payload_never_claims_live_broker_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.alerts.models import Alert, AlertType, Severity
    from app.core.alerts.slack_notifier import SlackNotifier

    captured: List[Dict[str, Any]] = []

    def _fake_post(url, payload, channel_key="default", timeout_sec=10.0):
        captured.append(payload)
        return True

    monkeypatch.setattr(
        "app.core.alerts.slack_dispatcher.get_webhook_for_channel",
        lambda ch: "https://hooks.example/signals",
    )
    monkeypatch.setattr("app.core.alerts.slack_dispatcher.post_slack_webhook", _fake_post)
    monkeypatch.setattr("app.core.alerts.slack_status.update_slack_status", lambda *a, **k: None)

    now = datetime.now(timezone.utc).isoformat()
    alert = Alert(
        alert_type=AlertType.POSITION_HOLD,
        severity=Severity.WARN,
        reason_code="DATA_UNRELIABLE",
        summary="Hold",
        action_hint="HOLD",
        fingerprint="fp-hold",
        created_at=now,
        symbol="SPY",
        meta={
            "lifecycle_format": "directive",
            "account_alias": "acct_individual",
            "broker_source": "manual_journal",
            "broker_state": "manual journal — not a LIVE Robinhood open",
            "strategy": "CSP",
            "expiration": "2026-09-19",
            "strike": 500,
            "right": "PUT",
            "quantity": 1,
            "contract_key": "SPY_20260919_P_500",
            "entry_credit": 1.25,
            "mark": 0.90,
            "mark_ts": now,
            "pnl_dollars": 35.0,
            "pnl_pct": 28.0,
            "dte": 37,
            "recommendation": "HOLD",
            "trigger": "DATA_UNRELIABLE",
            "reasons": ["DATA_UNRELIABLE", "quote stale"],
            "eval_run_id": "run-xyz",
        },
    )
    assert SlackNotifier({}).send(alert) is True
    body = captured[-1]
    text = body["text"]
    block_text = body["blocks"][0]["text"]["text"]
    assert "HOLD" in text
    assert "MANUAL ONLY — NO ORDER SENT" in text
    for needle in (
        "Account: acct_individual",
        "Broker source: manual_journal",
        "Symbol: SPY",
        "Strategy: CSP",
        "Quantity: 1",
        "DTE: 37",
        "Run ID: run-xyz",
        "MANUAL ONLY — NO ORDER SENT",
        "not a LIVE Robinhood open",
    ):
        assert needle in block_text
    assert "LIVE open position" not in block_text.lower()


def test_sanitize_and_retry_policy() -> None:
    from app.core.alerts.slack_dispatcher import post_slack_webhook, sanitize_slack_text

    dirty = "FAIL_FOO WARN_BAR token=abc https://hooks.slack.com/services/T/B/x C:\\Secrets\\a.txt"
    clean = sanitize_slack_text(dirty)
    assert "FAIL_" not in clean
    assert "WARN_" not in clean
    assert "hooks.slack.com" not in clean
    assert "token=[redacted]" in clean or "[redacted]" in clean
    assert "[path redacted]" in clean
    # Timestamps must not be corrupted by account-number heuristics.
    ts = "2026-08-13T16:45:59.954155+00:00"
    assert ".954155" in sanitize_slack_text(ts)
    assert ".[acct]" not in sanitize_slack_text(ts)

    class _Resp:
        def __init__(self, code, headers=None, text=""):
            self.status_code = code
            self.headers = headers or {}
            self.text = text

    calls = {"n": 0}

    def _post(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, {"Retry-After": "0"})
        return _Resp(200)

    with patch("app.core.alerts.slack_dispatcher._requests") as req:
        req.post.side_effect = _post
        # Bypass pacing sleep by stubbing pace
        with patch("app.core.alerts.slack_dispatcher._pace_channel", lambda *_a, **_k: None):
            with patch("app.core.alerts.slack_dispatcher.time.sleep", lambda *_a, **_k: None):
                assert post_slack_webhook("https://hooks.example/x", {"text": "hi"}, channel_key="signals") is True
        assert calls["n"] == 2

    calls["n"] = 0

    def _post_400(*a, **k):
        calls["n"] += 1
        return _Resp(400, text="bad")

    with patch("app.core.alerts.slack_dispatcher._requests") as req:
        req.post.side_effect = _post_400
        with patch("app.core.alerts.slack_dispatcher._pace_channel", lambda *_a, **_k: None):
            assert post_slack_webhook("https://hooks.example/x", {"text": "hi"}, channel_key="signals") is False
        assert calls["n"] == 1
