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

    monkeypatch.setenv("CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE", "1")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
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
    body = captured[-1]["blocks"][0]["text"]["text"]
    body_l = body.lower()
    text_l = captured[-1]["text"].lower()
    assert "not a live robinhood open" in body_l or "advisory" in text_l
    assert "EXIT IMMEDIATELY" not in body
    assert "EXIT ALL REMAINING" not in body
    assert "CLOSE POSITION ASAP" not in body
    assert "MANUAL REVIEW REQUIRED" in body
    assert "POSITION NOT CONFIRMED BY FRESH BROKER SNAPSHOT" in body
    assert "REFRESH ROBINHOOD BEFORE ACTING" in body
    assert "MANUAL ONLY — NO ORDER SENT" in body


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


def _spy_eligible_run(run_id: str = "eval_signal_spy_1") -> MagicMock:
    run = MagicMock()
    run.run_id = run_id
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 1
    run.eligible = 1
    run.symbols = [
        {
            "symbol": "SPY",
            "verdict": "ELIGIBLE",
            "score": 81.5,
            "band": "A",
            "strategy": "CSP",
            "primary_reason": "HIGH_CREDIT_QUALITY",
            "candidate_trades": [
                {
                    "strategy": "CSP",
                    "expiry": "2026-09-19",
                    "expiration": "2026-09-19",
                    "strike": 500.0,
                    "right": "P",
                    "suggested_quantity": 1,
                    "contract_key": "SPY_20260919_P_500",
                    "why_this_trade": "liquid CSP",
                }
            ],
        }
    ]
    run.top_candidates = list(run.symbols)
    run.errors = []
    run.regime = None
    return run


def test_ledger_from_artifact_eligible_identities_match():
    from app.core.eval.decision_artifact_v2 import CandidateRow, DecisionArtifactV2, SymbolEvalSummary
    from app.core.eval.eval_coordinator import _ledger_symbols_and_candidates_from_artifact

    artifact = DecisionArtifactV2(
        metadata={"mode": "LIVE"},
        symbols=[
            SymbolEvalSummary(
                symbol="SPY",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=81.5,
                band="A",
                primary_reason="HIGH_CREDIT_QUALITY",
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy="CSP",
                price=500.0,
                expiration="2026-09-19",
                has_candidates=True,
                candidate_count=1,
            )
        ],
        selected_candidates=[
            CandidateRow(
                symbol="SPY",
                strategy="CSP",
                expiry="2026-09-19",
                strike=500.0,
                delta=-0.2,
                credit_estimate=1.2,
                max_loss=49880.0,
                contract_key="SPY_20260919_P_500",
            )
        ],
        candidates_by_symbol={
            "SPY": [
                CandidateRow(
                    symbol="SPY",
                    strategy="CSP",
                    expiry="2026-09-19",
                    strike=500.0,
                    delta=-0.2,
                    credit_estimate=1.2,
                    max_loss=49880.0,
                    contract_key="SPY_20260919_P_500",
                )
            ]
        },
    )
    symbols, top = _ledger_symbols_and_candidates_from_artifact(artifact)
    assert symbols and top
    assert symbols[0]["symbol"] == "SPY"
    assert symbols[0]["verdict"] == "ELIGIBLE"
    assert symbols[0]["score"] == 81.5
    assert symbols[0]["band"] == "A"
    assert symbols[0]["strategy"] == "CSP"
    art_elig = {"SPY"}
    led_elig = {r["symbol"] for r in symbols if r.get("verdict") == "ELIGIBLE"}
    top_elig = {r["symbol"] for r in top}
    assert led_elig == art_elig == top_elig


def test_coordinator_passes_nonempty_symbols_and_top_candidates(monkeypatch):
    from app.core.eval import eval_coordinator as ec
    from app.core.eval.decision_artifact_v2 import CandidateRow, DecisionArtifactV2, SymbolEvalSummary

    saved = {}

    artifact = DecisionArtifactV2(
        metadata={
            "mode": "LIVE",
            "pipeline_timestamp": "2026-08-13T16:00:00+00:00",
            "eligible_count": 1,
            "universe_size": 1,
            "evaluated_count_stage1": 1,
            "evaluated_count_stage2": 1,
        },
        symbols=[
            SymbolEvalSummary(
                symbol="SPY",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=81.5,
                band="A",
                primary_reason="HIGH_CREDIT_QUALITY",
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy="CSP",
                price=500.0,
                expiration="2026-09-19",
                has_candidates=True,
                candidate_count=1,
            )
        ],
        selected_candidates=[
            CandidateRow(
                symbol="SPY",
                strategy="CSP",
                expiry="2026-09-19",
                strike=500.0,
                delta=-0.2,
                credit_estimate=1.2,
                max_loss=49880.0,
                contract_key="SPY_20260919_P_500",
            )
        ],
        candidates_by_symbol={},
    )
    artifact.started_at = "2026-08-13T16:00:00+00:00"
    artifact.completed_at = "2026-08-13T16:00:05+00:00"

    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "eval_ledger_1"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-13T16:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "eval_ledger_1"
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        lambda symbols, mode="LIVE", coordinator_run_id=None, output_dir=None: artifact,
    )
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", lambda run: saved.update(run=run))
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    monkeypatch.setattr("app.core.universe_v2.builder.build_universe_v2_snapshot", lambda: None)
    monkeypatch.setattr(
        "app.core.alerts.options_lifecycle_notifications.emit_options_lifecycle_notifications_from_run",
        lambda run: None,
    )
    monkeypatch.setattr("app.core.alerts.alert_engine.process_run_completed", lambda run: None)

    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="api")
    assert out.get("started") is True
    ledger = saved["run"]
    assert ledger.symbols
    assert ledger.top_candidates
    assert ledger.symbols[0]["symbol"] == "SPY"
    assert ledger.top_candidates[0]["symbol"] == "SPY"


def test_eligible_spy_signal_is_useful(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType
    from app.core.alerts.slack_notifier import SlackNotifier

    _patch_broker(monkeypatch, _fresh_snap())
    run = _spy_eligible_run()
    alerts = build_alerts_for_run(run, None, _load_alerts_config())
    signals = [a for a in alerts if a.alert_type == AlertType.SIGNAL]
    assert signals
    sig = signals[0]
    assert sig.symbol is None
    assert sig.meta.get("run_id") == run.run_id
    assert sig.meta.get("strategy") == "CSP"
    assert sig.meta.get("score") == 81.5
    assert sig.meta.get("band") == "A"
    assert "SPY" in (sig.summary or "")
    # Per-candidate CLEAR is allowed; aggregate CLEAR only if all checked.
    assert any(c.get("symbol") == "SPY" for c in (sig.meta.get("candidates") or []))
    preview = SlackNotifier({})._mobile_preview_text(sig)
    assert "NEW SETUP · ?" not in preview
    assert "SPY" in preview
    assert "CSP" in preview
    assert run.run_id in preview or "81.5" in preview
    assert "MANUAL ONLY — NO ORDER SENT" in preview


def test_aggregate_signal_symbol_none_never_clear(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType
    from app.core.portfolio.capital_authority_r70 import symbol_has_broker_conflict

    _patch_broker(monkeypatch, _fresh_snap())
    assert symbol_has_broker_conflict(None) is None
    run = MagicMock()
    run.run_id = "agg-none"
    run.status = "COMPLETED"
    run.symbols = []  # no eligible symbols → aggregate empty
    run.top_candidates = []
    run.eligible = 0
    run.errors = []
    run.regime = "RISK_ON"
    # Force set change vs previous with empty vs non-empty shortlist identity via previous_run
    prev = MagicMock()
    prev.symbols = [{"symbol": "ZZZ", "verdict": "ELIGIBLE"}]
    prev.top_candidates = [{"symbol": "ZZZ"}]
    prev.regime = "RISK_OFF"
    alerts = build_alerts_for_run(run, prev, _load_alerts_config())
    signals = [a for a in alerts if a.alert_type == AlertType.SIGNAL]
    assert signals
    label = signals[0].meta.get("robinhood_conflict_label") or ""
    assert "CLEAR" not in label
    assert signals[0].symbol is None
    assert "NOT PERFORMED" in label or "PARTIAL" in label


def test_fresh_aapl_clear_only_after_symbol_lookup(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType
    from app.core.portfolio.capital_authority_r70 import (
        get_broker_freshness_view,
        robinhood_conflict_check_label,
        symbol_has_broker_conflict,
    )

    _patch_broker(monkeypatch, _fresh_snap())
    view = get_broker_freshness_view("acct_individual")
    assert symbol_has_broker_conflict(None, freshness=view) is None
    assert symbol_has_broker_conflict("AAPL", freshness=view) is False
    assert "CLEAR" in robinhood_conflict_check_label(view["state"], conflict=False)

    run = MagicMock()
    run.run_id = "aapl-clear"
    run.status = "COMPLETED"
    run.symbols = [
        {
            "symbol": "AAPL",
            "verdict": "ELIGIBLE",
            "score": 70,
            "band": "B",
            "strategy": "CSP",
            "candidate_trades": [{"strategy": "CSP", "expiry": "2026-09-19", "strike": 180.0}],
        }
    ]
    run.top_candidates = list(run.symbols)
    run.errors = []
    run.regime = None
    alerts = build_alerts_for_run(run, None, _load_alerts_config())
    sig = next(a for a in alerts if a.alert_type == AlertType.SIGNAL)
    cand = (sig.meta.get("candidates") or [])[0]
    assert cand["robinhood_conflict"] is False
    assert "CLEAR" in cand["robinhood_conflict_label"]
    # Aggregate may say CLEAR only because every referenced symbol was checked.
    assert sig.meta.get("robinhood_conflict") is False
    assert "CLEAR" in (sig.meta.get("robinhood_conflict_label") or "")


def test_fresh_aapl_conflict_reports_conflict(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType

    _patch_broker(monkeypatch, _fresh_snap(conflict_symbol="AAPL"))
    run = MagicMock()
    run.run_id = "aapl-conflict"
    run.status = "COMPLETED"
    run.symbols = [
        {
            "symbol": "AAPL",
            "verdict": "ELIGIBLE",
            "score": 70,
            "band": "B",
            "strategy": "CSP",
            "candidate_trades": [{"strategy": "CSP", "expiry": "2026-09-19", "strike": 180.0}],
        }
    ]
    run.top_candidates = list(run.symbols)
    run.errors = []
    run.regime = None
    alerts = build_alerts_for_run(run, None, _load_alerts_config())
    sig = next(a for a in alerts if a.alert_type == AlertType.SIGNAL)
    assert sig.meta.get("robinhood_conflict") is True
    assert "CONFLICT" in (sig.meta.get("robinhood_conflict_label") or "")
    assert "CONFLICT" in ((sig.meta.get("candidates") or [])[0]["robinhood_conflict_label"])


def test_same_counts_different_symbols_different_fingerprints(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType

    _patch_broker(monkeypatch, None)

    def _run(syms):
        r = MagicMock()
        r.run_id = "fp-" + "-".join(syms)
        r.status = "COMPLETED"
        r.symbols = [
            {
                "symbol": s,
                "verdict": "ELIGIBLE",
                "score": 70,
                "band": "B",
                "strategy": "CSP",
                "candidate_trades": [{"strategy": "CSP"}],
            }
            for s in syms
        ]
        r.top_candidates = list(r.symbols)
        r.errors = []
        r.regime = None
        return r

    a1 = build_alerts_for_run(_run(["AAA", "BBB"]), None, _load_alerts_config())
    a2 = build_alerts_for_run(_run(["CCC", "DDD"]), None, _load_alerts_config())
    s1 = next(a for a in a1 if a.alert_type == AlertType.SIGNAL)
    s2 = next(a for a in a2 if a.alert_type == AlertType.SIGNAL)
    assert s1.fingerprint != s2.fingerprint


def test_effective_stale_never_displayed_as_fresh(monkeypatch):
    from app.core.alerts.models import Alert, AlertType, Severity
    from app.core.alerts.slack_notifier import SlackNotifier
    from app.core.portfolio.capital_authority_r70 import get_broker_freshness_view

    # Raw snap freshness="fresh" but age makes effective STALE.
    _patch_broker(monkeypatch, _fresh_snap(age_minutes=200, stale=False))
    view = get_broker_freshness_view("acct_individual")
    assert view["state"] == "STALE"
    assert view.get("freshness") == "fresh"

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
        action_hint="REVIEW",
        fingerprint="fp-stale-disp",
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol="SPY",
        meta={
            "lifecycle_format": "directive",
            "live_confirmed": False,
            "broker_freshness": view["state"],
            "freshness": view["state"],
            "freshness_state": view["state"],
            "snapshot_age": view.get("age_minutes"),
            "broker_state": "advisory/unverified — broker STALE; refresh required",
            "quantity": 1,
            "eval_run_id": "eval_stale_disp",
        },
    )
    SlackNotifier({}).send(alert)
    body = captured[-1]["blocks"][0]["text"]["text"]
    assert "/ fresh" not in body.lower().split("freshness:")[-1] if "freshness:" in body.lower() else True
    assert "STALE" in body
    assert "freshness=fresh" not in body.lower()
    assert "EXIT IMMEDIATELY" not in body


def test_concurrent_same_channel_pacing_and_cross_channel(monkeypatch):
    import threading
    import time

    from app.core.alerts import slack_dispatcher as sd

    monkeypatch.setattr(sd, "_CHANNEL_MIN_INTERVAL_SEC", 0.25)
    sd._next_channel_send_monotonic.clear()
    sd._last_channel_send_monotonic.clear()
    sd._CHANNEL_LOCKS.clear()

    same_times: List[float] = []
    cross_times: Dict[str, List[float]] = {"signals": [], "daily": []}
    barrier = threading.Barrier(2)

    def _same():
        barrier.wait(timeout=5)
        t0 = time.monotonic()
        sd._pace_channel("signals")
        same_times.append(time.monotonic() - t0)

    t1 = threading.Thread(target=_same)
    t2 = threading.Thread(target=_same)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert len(same_times) == 2
    assert max(same_times) >= 0.20  # one waiter reserved ~interval later

    sd._next_channel_send_monotonic.clear()
    sd._last_channel_send_monotonic.clear()
    barrier2 = threading.Barrier(2)

    def _cross(ch: str):
        barrier2.wait(timeout=5)
        t0 = time.monotonic()
        sd._pace_channel(ch)
        cross_times[ch].append(time.monotonic() - t0)

    ta = threading.Thread(target=_cross, args=("signals",))
    tb = threading.Thread(target=_cross, args=("daily",))
    ta.start()
    tb.start()
    ta.join(timeout=5)
    tb.join(timeout=5)
    # Different channels should not wait on each other (both near-instant).
    assert cross_times["signals"][0] < 0.15
    assert cross_times["daily"][0] < 0.15


def test_clear_notification_state_cannot_touch_canonical(monkeypatch, tmp_path):
    from app.core.alerts import alert_engine as ae

    # Path shaped like production out/alerts (even under pytest temp).
    canonical = tmp_path / "project" / "out" / "alerts"
    canonical.mkdir(parents=True)
    state = canonical / "notification_delivery_state.json"
    state.write_text('{"runs":{"keep":{}},"order":["keep"]}', encoding="utf-8")

    monkeypatch.delenv("CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE", raising=False)
    monkeypatch.setattr(ae, "_get_alerts_dir", lambda: canonical)
    with pytest.raises(RuntimeError, match="Refusing to clear canonical"):
        ae.clear_notification_idempotency_state()
    assert state.exists()
    assert "keep" in state.read_text(encoding="utf-8")

    # Isolated path + guard may clear.
    iso = tmp_path / "iso_alerts"
    iso.mkdir()
    monkeypatch.setenv("CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE", "1")
    monkeypatch.setattr(ae, "_get_alerts_dir", lambda: iso)
    ae.clear_notification_idempotency_state()
    assert (iso / "notification_delivery_state.json").exists()


def test_failed_live_no_success_summary_or_trading_signal(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run, process_run_completed
    from app.core.alerts.models import AlertType

    failed = MagicMock()
    failed.run_id = "fail-live-1"
    failed.status = "FAILED"
    failed.error_summary = "boom"
    failed.symbols = [
        {
            "symbol": "SPY",
            "verdict": "ELIGIBLE",
            "score": 90,
            "band": "A",
            "strategy": "CSP",
            "candidate_trades": [{"strategy": "CSP"}],
        }
    ]
    failed.top_candidates = list(failed.symbols)
    failed.errors = ["boom"]
    failed.regime = None
    alerts = build_alerts_for_run(failed, None, _load_alerts_config())
    assert all(a.alert_type != AlertType.SIGNAL for a in alerts)
    assert any(a.alert_type == AlertType.SYSTEM for a in alerts)

    summary_calls: List[Any] = []
    signal_sends: List[Any] = []
    with patch(
        "app.core.alerts.slack_notifier.SlackNotifier.send_eval_summary",
        side_effect=lambda ch, payload: summary_calls.append(payload) or True,
    ):
        with patch(
            "app.core.alerts.slack_notifier.SlackNotifier.send",
            side_effect=lambda alert: signal_sends.append(alert) or True,
        ):
            with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
                process_run_completed(failed)
    assert summary_calls == []
    assert all(
        (a.alert_type.value if hasattr(a.alert_type, "value") else a.alert_type) != "SIGNAL"
        for a in signal_sends
    )
    assert any(
        (a.alert_type.value if hasattr(a.alert_type, "value") else a.alert_type) == "SYSTEM"
        for a in signal_sends
    )


def test_paper_rejected_skipped_produce_nothing(monkeypatch):
    from app.core.eval import eval_coordinator as ec

    calls: List[Any] = []
    monkeypatch.setattr("app.core.alerts.alert_engine.process_run_completed", lambda run: calls.append(run))
    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (False, "already_running"))
    out = ec.run_universe_evaluation_exclusive(["SPY"], mode="LIVE", trigger="api")
    assert out.get("started") is False
    assert calls == []

    artifact = SimpleNamespace(
        symbols=[],
        metadata={"universe_size": 0, "evaluated_count_stage1": 0, "eligible_count": 0, "market_phase": "OPEN"},
        started_at="2026-08-13T12:00:00+00:00",
        completed_at="2026-08-13T12:00:01+00:00",
    )
    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "paper-2"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-13T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "paper-2"
    monkeypatch.setattr(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        lambda symbols, mode="LIVE", coordinator_run_id=None, output_dir=None: artifact,
    )
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", lambda run: None)
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    monkeypatch.setattr("app.core.universe_v2.builder.build_universe_v2_snapshot", lambda: None)
    out2 = ec.run_universe_evaluation_exclusive(["SPY"], mode="PAPER", trigger="api", allow_when_closed=True)
    assert out2.get("started") is True
    assert calls == []
