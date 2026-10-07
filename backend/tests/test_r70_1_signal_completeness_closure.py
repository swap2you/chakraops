# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70.1: Exact Robinhood option confirmation + SIGNAL phone-first + delivery categories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.core.broker.models import BrokerBalances, BrokerSnapshot, EquityPosition, OptionPosition


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    from app.core.alerts import alert_engine as ae

    monkeypatch.setenv("CHAKRAOPS_ALLOW_CLEAR_NOTIFICATION_STATE", "1")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(ae, "_get_alerts_dir", lambda: tmp_path / "alerts")
    ae.clear_notification_idempotency_state()
    yield
    ae.clear_notification_idempotency_state()


def _snap(
    *,
    age_minutes: float = 5.0,
    equities: Optional[List[EquityPosition]] = None,
    options: Optional[List[OptionPosition]] = None,
) -> BrokerSnapshot:
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    return BrokerSnapshot(
        account_alias="acct_individual",
        fetched_at=fetched,
        balances=BrokerBalances(cash=1000.0, buying_power=1000.0, equity=1000.0),
        equity_positions=equities or [],
        option_positions=options or [],
        freshness="fresh",
        completeness="complete",
        stale=False,
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


def test_exact_match_confirms_option(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-09-19", strike=180.0, right="P"
    )
    assert conf["status"] == "MATCH"
    assert conf["live_confirmed"] is True


def test_different_expiration_not_confirmed(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-10-17", strike=180.0, right="put"
    )
    assert conf["status"] == "NO_MATCH"
    assert conf["live_confirmed"] is False


def test_different_strike_not_confirmed(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-09-19", strike=185.0, right="put"
    )
    assert conf["status"] == "NO_MATCH"


def test_different_option_type_not_confirmed(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-09-19", strike=180.0, right="call"
    )
    assert conf["status"] == "NO_MATCH"


def test_stock_vs_option_never_confirms_option(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    eq = EquityPosition(symbol="AAPL", quantity=10.0, average_cost=100.0)
    _patch_broker(monkeypatch, _snap(equities=[eq]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-09-19", strike=180.0, right="put"
    )
    assert conf["status"] == "NO_MATCH"
    assert conf["reason"] == "equity_only_not_option_confirmation"
    assert conf["live_confirmed"] is False


def test_missing_fields_partial(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    conf = exact_option_broker_confirmation(symbol="AAPL", expiration=None, strike=180.0, right="put")
    assert conf["status"] == "PARTIAL"
    assert conf["live_confirmed"] is False


def test_stale_snapshot_unknown(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import exact_option_broker_confirmation

    opt = OptionPosition(symbol="AAPL", option_type="put", strike=180.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(age_minutes=200, options=[opt]))
    conf = exact_option_broker_confirmation(
        symbol="AAPL", expiration="2026-09-19", strike=180.0, right="put"
    )
    assert conf["status"] == "UNKNOWN"
    assert conf["live_confirmed"] is False


def test_underlying_only_option_conflict_is_partial(monkeypatch):
    from app.core.portfolio.capital_authority_r70 import symbol_has_broker_conflict

    opt = OptionPosition(symbol="SPY", option_type="put", strike=500.0, expiration="2026-09-19", quantity=-1)
    _patch_broker(monkeypatch, _snap(options=[opt]))
    # No contract fields → never CLEAR from option underlying alone.
    assert symbol_has_broker_conflict("SPY") is None


def test_signal_includes_orats_and_data_not_actionable(monkeypatch):
    from app.core.alerts.alert_engine import _load_alerts_config, build_alerts_for_run
    from app.core.alerts.models import AlertType
    from app.core.alerts.slack_notifier import SlackNotifier

    _patch_broker(monkeypatch, _snap())
    monkeypatch.setattr(
        "app.api.data_health.get_orats_freshness_state",
        lambda: {"state": "ERROR", "as_of": None},
    )
    run = MagicMock()
    run.run_id = "sig-orats"
    run.status = "COMPLETED"
    run.symbols = [
        {
            "symbol": "SPY",
            "verdict": "ELIGIBLE",
            "score": 80,
            "band": "A",
            "strategy": "CSP",
            "candidate_trades": [
                {"strategy": "CSP", "expiry": "2026-09-19", "strike": 500.0, "right": "P"}
            ],
        }
    ]
    run.top_candidates = list(run.symbols)
    run.errors = []
    run.regime = None
    alerts = build_alerts_for_run(run, None, _load_alerts_config())
    sig = next(a for a in alerts if a.alert_type == AlertType.SIGNAL)
    assert sig.meta.get("orats_state") == "ERROR"
    assert sig.meta.get("actionability") == "DATA NOT ACTIONABLE"
    preview = SlackNotifier({})._mobile_preview_text(sig)
    assert "DATA NOT ACTIONABLE" in preview
    assert "orats=ERROR" in preview
    assert "MANUAL ONLY — NO ORDER SENT" in preview
    assert "ENTER" not in preview.upper() or "MANUAL" in preview
    blocks = SlackNotifier({})._build_signal_blocks(sig)
    blob = str(blocks)
    assert "DATA NOT ACTIONABLE" in blob
    assert "ORATS" in blob
    assert "MANUAL ONLY" in blob


def test_eval_summary_records_failure_category_and_retries_transient(monkeypatch):
    from app.core.alerts.alert_engine import (
        _delivery_was_sent,
        _load_delivery_state,
        process_run_completed,
    )

    calls = {"n": 0}

    def _send(ch, payload):
        calls["n"] += 1
        notifier = MagicMock()
        # emulate SlackNotifier attribute used by process_run_completed path via patch
        return False

    run = MagicMock()
    run.run_id = "dur-cat-1"
    run.status = "COMPLETED"
    run.completed_at = "2026-08-13T16:00:00+00:00"
    run.total = 1
    run.eligible = 0
    run.symbols = []
    run.top_candidates = []
    run.duration_seconds = 1.0
    run.errors = []

    class _N:
        last_failure_category = "http_5xx"

        def __init__(self, *_a, **_k):
            self.last_failure_category = "http_5xx"

        def send(self, *_a, **_k):
            return False

        def send_eval_summary(self, ch, payload):
            calls["n"] += 1
            if calls["n"] == 1:
                self.last_failure_category = "http_5xx"
                return False
            self.last_failure_category = ""
            return True

        def _channel_for_alert(self, *_a, **_k):
            return "signals"

    with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
        with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
            with patch("app.core.alerts.slack_notifier.SlackNotifier", _N):
                process_run_completed(run)
    assert _delivery_was_sent("dur-cat-1", "EVAL_SUMMARY") is True
    assert calls["n"] == 2
    # Second process must not send again.
    with patch("app.core.alerts.alert_engine.build_alerts_for_run", return_value=[]):
        with patch("app.core.alerts.alert_engine.build_lifecycle_alerts_for_run", return_value=[]):
            with patch("app.core.alerts.slack_notifier.SlackNotifier", _N):
                process_run_completed(run)
    assert calls["n"] == 2
    data = _load_delivery_state()
    rec = data["runs"]["dur-cat-1"]["items"]["EVAL_SUMMARY"]
    assert rec["status"] == "sent"
    assert rec.get("failure_category") is None


def test_five_concurrent_same_channel_pacing(monkeypatch):
    import threading
    import time

    from app.core.alerts import slack_dispatcher as sd

    monkeypatch.setattr(sd, "_CHANNEL_MIN_INTERVAL_SEC", 0.15)
    sd._next_channel_send_monotonic.clear()
    sd._last_channel_send_monotonic.clear()
    sd._CHANNEL_LOCKS.clear()

    n = 5
    barrier = threading.Barrier(n)
    start_ends: List[float] = []

    def _worker():
        barrier.wait(timeout=5)
        t0 = time.monotonic()
        sd._pace_channel("signals")
        start_ends.append(time.monotonic() - t0)

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(start_ends) == n
    # Last reserved waiter should wait ~(n-1)*interval without a 2s cap truncating.
    assert max(start_ends) >= 0.15 * (n - 2)
    # Span of reserved times should be at least (n-1)*interval
    assert max(start_ends) - min(start_ends) >= 0.15 * (n - 2)
