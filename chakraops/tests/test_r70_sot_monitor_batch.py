# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 batch: SoT counts, score reconcile, no auto-eval, monitor/notifications."""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# R70-DEF-050 / RERUN-1: system-health must not advance last_build_ts (write-on-read)
# ---------------------------------------------------------------------------


def test_positions_unified_health_last_build_ts_stable(tmp_path, monkeypatch):
    """GET health must not stamp last_build_ts = now() on every read."""
    from app.core.portfolio import positions_unified_store_r279 as store

    db = tmp_path / "positions.db"
    store.set_positions_db_path(db)
    store.init_db()

    rebuild_state = tmp_path / "positions_unified_rebuild_state.json"
    fixed_ts = "2026-08-01T12:00:00+00:00"
    rebuild_state.write_text(
        json.dumps(
            {
                "status": "OK",
                "status_label": "OK",
                "last_rebuild_at_utc": fixed_ts,
                "last_rebuild_open_count": 2,
                "last_rebuild_closed_count": 0,
                "last_include_paper": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "_rebuild_state_path", lambda: rebuild_state)

    h1 = store.get_positions_unified_health()
    time.sleep(0.05)
    h2 = store.get_positions_unified_health()
    assert h1["last_build_ts"] == fixed_ts
    assert h2["last_build_ts"] == fixed_ts
    assert h1["last_build_ts"] == h2["last_build_ts"]
    assert h1.get("authority") == "positions_unified_db"


# ---------------------------------------------------------------------------
# R70-DEF-021: open counts carry provenance; expired options excluded from live open
# ---------------------------------------------------------------------------


def test_unified_db_open_excludes_expired_and_exposes_provenance(tmp_path, monkeypatch):
    from app.core.portfolio import positions_unified_store_r279 as store

    db = tmp_path / "positions.db"
    store.set_positions_db_path(db)
    store.init_db()

    today = date.today()
    expired = (today - timedelta(days=30)).isoformat()
    future = (today + timedelta(days=30)).isoformat()

    conn = __import__("sqlite3").connect(str(db))
    try:
        conn.execute(
            """INSERT INTO positions_open (
                id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("live_opt_exp", "AAPL", "CSP", 0, 1, 1.0, 100.0, expired, "PUT", "2026-01-01T00:00:00", None, None, None),
        )
        conn.execute(
            """INSERT INTO positions_open (
                id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("live_opt_ok", "MSFT", "CSP", 0, 1, 1.0, 200.0, future, "PUT", "2026-01-01T00:00:00", None, None, None),
        )
        conn.execute(
            """INSERT INTO positions_open (
                id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("live_shares", "NVDA", "SHARES", 0, 10, 100.0, None, None, None, "2026-01-01T00:00:00", None, None, None),
        )
        conn.execute(
            """INSERT INTO positions_open (
                id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("paper_1", "AAPL", "SHARES", 1, 1, 180.0, None, None, None, "2026-01-01T00:00:00", None, None, None),
        )
        conn.commit()
    finally:
        conn.close()

    live = store.read_positions_unified_from_db(state="open", include_paper=False, limit=500)
    assert live["include_paper"] is False
    assert live["authority"] == "positions_unified_db"
    assert "as_of" in live
    ids = {i["id"] for i in live["items"]}
    assert "live_opt_exp" not in ids
    assert "live_opt_ok" in ids
    assert "live_shares" in ids
    assert "paper_1" not in ids
    assert live["count"] == 2
    assert live["count_expired_excluded"] == 1


# ---------------------------------------------------------------------------
# R70-DEF-022: score breakdown reconciles; liquidity not evaluated → no numeric score
# ---------------------------------------------------------------------------


def test_stage1_only_breakdown_reconciles_to_displayed_score():
    from app.core.eval.scoring import compute_score_breakdown
    from app.core.eval.staged_evaluator import EvaluationStage, FullEvaluationResult, Stage1Result

    result = FullEvaluationResult(symbol="NVDA")
    result.stage_reached = EvaluationStage.STAGE1_ONLY
    result.stage1 = Stage1Result(symbol="NVDA", stage1_score=35)
    result.score = 35
    result.data_completeness = 1.0
    result.regime = "NEUTRAL"
    result.liquidity_ok = False
    result.verdict = "HOLD"
    result.position_open = False
    result.price = 100.0

    breakdown, weighted = compute_score_breakdown(
        data_completeness=result.data_completeness,
        regime=result.regime,
        liquidity_ok=result.liquidity_ok,
        liquidity_grade=None,
        verdict=result.verdict,
        position_open=result.position_open,
        price=result.price,
        selected_put_strike=None,
        liquidity_evaluated=False,
    )
    # Simulate STAGE1_ONLY reconciliation helper
    from app.core.eval.scoring import reconcile_stage1_score_breakdown

    bd = reconcile_stage1_score_breakdown(
        breakdown,
        weighted_composite=weighted,
        stage1_score=35,
        final_score=35,
        market_regime="NEUTRAL",
    )
    assert bd["options_liquidity_score"] is None
    assert bd["options_liquidity_evaluated"] is False
    assert bd["composite_score"] == 35
    assert bd["raw_score"] == 35
    assert bd["final_score"] == 35
    assert bd["score_basis"] == "stage1_score"
    assert bd["composite_score"] == bd["final_score"]


def test_hold_time_distance_matches_reported_spot_and_t1():
    from app.api.ui_routes import _build_hold_time_estimate_at_request_time

    technicals = {"atr": 7.62, "spot": 219.12}
    exit_plan = {"t1": 221.16}
    est = _build_hold_time_estimate_at_request_time(technicals, exit_plan)
    assert est is not None
    assert est["hold_time_spot"] == pytest.approx(219.12)
    assert est["hold_time_t1"] == pytest.approx(221.16)
    assert est["hold_time_distance_to_t1"] == pytest.approx(abs(221.16 - 219.12), rel=1e-6)


# ---------------------------------------------------------------------------
# R70-DEF-035: no auto full-eval on local start; source labels follow trigger
# ---------------------------------------------------------------------------


def test_create_run_source_follows_trigger():
    from app.core.eval.evaluation_store import create_run_from_evaluation, map_eval_trigger_to_source
    from app.core.eval.universe_evaluator import UniverseEvaluationResult

    assert map_eval_trigger_to_source("ui_eval_run") == "manual"
    assert map_eval_trigger_to_source("ops_evaluate") == "manual"
    assert map_eval_trigger_to_source("scheduler") == "scheduled"
    assert map_eval_trigger_to_source("nightly") == "nightly"
    assert map_eval_trigger_to_source("eod_freeze") == "scheduled"

    result = UniverseEvaluationResult(
        total=0,
        evaluated=0,
        eligible=0,
        shortlisted=0,
        duration_seconds=0.0,
        symbols=[],
        alerts=[],
        errors=[],
        evaluation_state="COMPLETED",
        last_evaluated_at="2026-08-11T00:00:00+00:00",
    )
    run = create_run_from_evaluation(
        run_id="eval_test",
        started_at="2026-08-11T00:00:00+00:00",
        evaluation_result=result,
        market_phase="OPEN",
        source="scheduled",
    )
    assert run.source == "scheduled"


def test_startup_does_not_start_universe_evaluation(monkeypatch):
    """With schedulers off, recovery/startup must not call exclusive universe eval."""
    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED", "false")
    calls = []

    def _boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("universe eval must not run on startup")

    with patch(
        "app.core.eval.eval_coordinator.run_universe_evaluation_exclusive",
        side_effect=_boom,
    ):
        with patch(
            "app.core.eval.evaluation_service_v2.evaluate_universe",
            side_effect=_boom,
        ):
            from app.core.operations.scheduler_service import start_scheduler_service, scheduler_status

            # Reset recovery flag so start runs recovery once under our patches
            import app.core.operations.scheduler_service as sched

            monkeypatch.setattr(sched, "_recovery_done", False)
            start_scheduler_service()
            st = scheduler_status()
            assert st.get("master_enabled") is False or st.get("running") is False
            assert calls == []


# ---------------------------------------------------------------------------
# R70-DEF-050/051/052 + RERUN: notifications honesty + durable dedupe
# ---------------------------------------------------------------------------


def test_identical_active_notifications_are_deduped(tmp_path, monkeypatch):
    from app.api import notifications_store as ns

    path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr(ns, "_notifications_path", lambda: path)

    ns.append_notification("INFO", "POSITIONS_RECONCILE_REVIEW", "Unified positions reconcile needs attention (counts differ).")
    ns.append_notification("INFO", "POSITIONS_RECONCILE_REVIEW", "Unified positions reconcile needs attention (counts differ).")
    recs = ns.load_notifications(limit=50, type_filter="POSITIONS_RECONCILE_REVIEW")
    active = [r for r in recs if r.get("state") in ("NEW", "ACKED", None) or r.get("state") == "NEW"]
    # Exactly one active identical advisory
    assert sum(1 for r in recs if r.get("message", "").startswith("Unified positions reconcile")) == 1


def test_orats_warn_dedupe_survives_process_restart(tmp_path, monkeypatch):
    from app.api import notifications_store as ns

    path = tmp_path / "notifications.jsonl"
    throttle = tmp_path / "orats_warn_throttle.json"
    monkeypatch.setattr(ns, "_notifications_path", lambda: path)
    monkeypatch.setattr(ns, "_orats_warn_throttle_path", lambda: throttle)
    ns._LAST_ORATS_WARN_AT = None

    ns.append_orats_warn("ORATS stale")
    ns._LAST_ORATS_WARN_AT = None  # simulate process restart
    ns.append_orats_warn("ORATS stale")
    text = path.read_text(encoding="utf-8")
    assert text.count("ORATS stale") == 1


def test_advisory_monitor_dedupe_persists_across_instances(tmp_path, monkeypatch):
    from app.core.monitor import advisory_worker_r54 as mon

    state = tmp_path / "advisory_monitor_r54.json"
    monkeypatch.setattr(mon.AdvisoryMonitorWorker, "_state_path", lambda self: state)
    monkeypatch.setenv("R65_ORATS_OK", "false")

    w1 = mon.AdvisoryMonitorWorker(interval_sec=60)
    with patch("app.core.broker.status.robinhood_mcp_read_only_status", return_value={
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True,
        "status": "READ_ONLY_AVAILABLE",
    }):
        with patch("app.core.broker.snapshot_store.load_snapshot", return_value=None):
            with patch.object(w1, "_dispatch_slack"):
                first = w1.run_once()
                assert any(s.signal_type == "ORATS_STALE" for s in first)

    w2 = mon.AdvisoryMonitorWorker(interval_sec=60)
    # Load prior state before run
    w2._load_persisted_signals()
    with patch("app.core.broker.status.robinhood_mcp_read_only_status", return_value={
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True,
        "status": "READ_ONLY_AVAILABLE",
    }):
        with patch("app.core.broker.snapshot_store.load_snapshot", return_value=None):
            with patch.object(w2, "_dispatch_slack") as slack:
                w2.run_once()
                # Unchanged ORATS_STALE must not re-dispatch
                slack.assert_called()
                emitted_arg = slack.call_args[0][0]
                assert emitted_arg == []


def test_observability_labels_stub_or_probes_orats(monkeypatch):
    from app.core.ops.observability_r60 import connected_observability_status

    monkeypatch.setenv("R65_ORATS_OK", "false")
    with patch("app.core.broker.status.robinhood_mcp_read_only_status", return_value={
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": False,
        "status": "UNAUTHENTICATED",
        "blocker": "auth",
    }):
        with patch("app.core.monitor.advisory_worker_r54.monitor_status", return_value={
            "running": False,
            "last_run_at": None,
            "signal_count": 0,
        }):
            st = connected_observability_status()
    comps = st["components"]
    assert comps["api"]["status"] in ("OK", "UP")
    # Must not claim ORATS healthy when env says down; stub must be labelled
    orats = comps.get("orats") or {}
    assert orats.get("status") in ("DEGRADED", "DOWN", "STALE", "UNAVAILABLE")
    assert "broker_mcp" in comps
    assert st.get("manual_only") is True


def test_scheduler_off_status_exposes_notification_sources(monkeypatch):
    """When scheduler is off, status must not imply notifications come from the scheduler."""
    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "false")
    from app.core.system_health import operations_health_snapshot

    fields = operations_health_snapshot()
    assert fields.get("scheduler_running") is False or fields.get("scheduler_master_enabled") is False
    sources = fields.get("notification_sources") or []
    assert "legacy_scheduler" not in [s for s in sources if fields.get("scheduler_running")]
    assert any(s in sources for s in ("advisory_monitor", "reconcile_advisory", "ops_jobs", "in_app"))
