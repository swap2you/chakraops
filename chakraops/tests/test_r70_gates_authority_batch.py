# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-040/041/042: eval authority, macro/session gates, holiday hours."""

from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import pytest


# ---------------------------------------------------------------------------
# R70-DEF-040 — single LIVE eval authority
# ---------------------------------------------------------------------------


def test_r70_def040_evaluate_now_uses_exclusive_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/ops/evaluate-now must route through exclusive coordinator (not staged bypass)."""
    import app.api.server as server

    called: Dict[str, Any] = {}

    def fake_exclusive(symbols, *, mode="LIVE", trigger="api"):
        called["symbols"] = list(symbols)
        called["mode"] = mode
        called["trigger"] = trigger
        return {
            "started": True,
            "reason": "ok",
            "run_id": "coord-now-1",
            "counts": {"universe_size": len(symbols)},
        }

    monkeypatch.setattr(
        "app.core.eval.eval_coordinator.run_universe_evaluation_exclusive",
        fake_exclusive,
    )
    monkeypatch.setattr("app.api.data_health.UNIVERSE_SYMBOLS", ["SPY", "AAPL"], raising=False)
    monkeypatch.setattr(
        "app.api.data_health.get_universe_symbols",
        lambda: ["SPY", "AAPL"],
        raising=False,
    )

    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    resp = client.post("/api/ops/evaluate-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("started") is True
    assert body.get("exclusive") is True
    assert body.get("authority") == "PRIMARY_LIVE_EVAL"
    assert called.get("trigger") == "ops_evaluate_now"
    assert called.get("mode") == "LIVE"


def test_r70_def040_primary_authority_markers() -> None:
    from app.core.eval import eval_coordinator

    assert getattr(eval_coordinator, "PRIMARY_LIVE_EVAL_AUTHORITY", None) is True
    assert hasattr(eval_coordinator, "run_universe_evaluation_exclusive")


def test_r70_def040_secondary_paths_are_labeled() -> None:
    """Offline/dev harness and single-symbol merge must be marked secondary."""
    import scripts.offline_eval_proof as offline
    import scripts.run_and_save as ras
    from app.core.eval import evaluation_service_v2 as v2

    assert getattr(offline, "SECONDARY_EVAL_PATH", False) is True
    assert getattr(ras, "SECONDARY_EVAL_PATH", False) is True
    assert getattr(v2, "SECONDARY_SYMBOL_MERGE_PATH", False) is True


def test_r70_def040_direct_universe_evaluator_inventory_is_closed() -> None:
    """Every production/script caller is known; only the coordinator may request LIVE."""
    root = Path(__file__).resolve().parents[1]
    callers: dict[str, list[str | None]] = {}

    for source_root in (root / "app", root / "scripts"):
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else None
                )
                if name != "evaluate_universe":
                    continue
                mode: str | None = None
                for keyword in node.keywords:
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                        mode = keyword.value.value
                relative = source_path.relative_to(root).as_posix()
                callers.setdefault(relative, []).append(mode)

    assert callers == {
        "app/core/eval/eval_coordinator.py": [None],
        "scripts/offline_eval_proof.py": ["PAPER"],
        "scripts/run_and_save.py": ["PAPER"],
    }


def test_r70_def040_live_universe_authority_fails_closed_outside_coordinator() -> None:
    from app.core.eval import evaluation_service_v2 as service
    from app.core.eval.evaluation_store_v2 import (
        DECISION_STORE_PATH,
        get_decision_store_path,
        reset_output_dir,
        set_output_dir,
    )

    # Point the in-memory store at the true canonical path without writing.
    set_output_dir(DECISION_STORE_PATH.parent)
    try:
        assert get_decision_store_path().resolve() == DECISION_STORE_PATH.resolve()
        assert service._canonical_live_universe_write_is_authorized() is False
        with pytest.raises(PermissionError, match="eval_coordinator"):
            service._require_live_universe_write_authority("LIVE")
        service._require_live_universe_write_authority("PAPER")
    finally:
        reset_output_dir()


def test_reset_output_dir_honors_out_dir_env_and_does_not_target_canonical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core.eval.evaluation_store_v2 import (
        DECISION_STORE_PATH,
        get_decision_store_path,
        reset_output_dir,
        set_output_dir,
    )

    isolated = tmp_path / "isolated_out"
    isolated.mkdir()
    monkeypatch.setenv("OUT_DIR", str(isolated))
    set_output_dir(tmp_path / "other")
    reset_output_dir()
    restored = get_decision_store_path().resolve()
    assert restored == (isolated / "decision_latest.json").resolve()
    assert restored != DECISION_STORE_PATH.resolve()


def test_r70_def040_coordinator_scope_is_private_to_coordinator_source() -> None:
    """No script or API route may acquire the coordinator's process-local capability."""
    root = Path(__file__).resolve().parents[1]
    needle = "_coordinator_live_universe_write_scope"
    owners = {
        path.relative_to(root).as_posix()
        for source_root in (root / "app", root / "scripts")
        for path in source_root.rglob("*.py")
        if needle in path.read_text(encoding="utf-8")
    }
    assert owners == {
        "app/core/eval/eval_coordinator.py",
        "app/core/eval/evaluation_service_v2.py",
    }


# ---------------------------------------------------------------------------
# R70-DEF-041 — macro/session gates fail-closed / wired
# ---------------------------------------------------------------------------


def test_r70_def041_macro_gate_fail_closed_when_unconfigured() -> None:
    from app.core.environment.event_calendar import DefaultEventCalendar
    from app.core.environment.macro_event_gate import check_macro_event_gate

    reason = check_macro_event_gate(
        DefaultEventCalendar(),
        {"macro_event_block_window_days": 2},
        provider_configured=False,
    )
    assert reason is not None
    assert reason.code == "MACRO_CALENDAR_UNAVAILABLE"


def test_r70_def041_macro_gate_blocks_known_fomc() -> None:
    from datetime import timedelta

    from app.core.environment.event_calendar import Event, StaticUsMacroCalendar
    from app.core.environment.macro_event_gate import check_macro_event_gate

    # Inject calendar with FOMC tomorrow so window=2 catches it.
    tomorrow = date.today() + timedelta(days=1)
    cal = StaticUsMacroCalendar(events=[Event(name="FOMC", date=tomorrow)])
    reason = check_macro_event_gate(
        cal,
        {"macro_event_block_window_days": 2},
        provider_configured=True,
    )
    assert reason is not None
    assert reason.code == "MACRO_EVENT_WINDOW"


def test_r70_def041_macro_gate_configured_empty_passes() -> None:
    from app.core.environment.event_calendar import DefaultEventCalendar
    from app.core.environment.macro_event_gate import check_macro_event_gate

    reason = check_macro_event_gate(
        DefaultEventCalendar(),
        {"macro_event_block_window_days": 2},
        provider_configured=True,
    )
    assert reason is None


def test_r70_def041_session_gate_wired_in_decision_engine() -> None:
    from datetime import timezone

    from app.core.decision_engine.contract import CSP, DecisionInput, OptionContract, PortfolioState
    from app.core.decision_engine.engine import evaluate_candidate
    from app.core.decision_engine.profiles import get_profile

    # Christmas Eve 2026 is a short session → SHORT_SESSION block.
    now = datetime(2026, 12, 24, 15, 0, tzinfo=timezone.utc)
    # 15:00 UTC = 10:00 ET on Dec 24 2026 (weekday short session).
    today_et = date(2026, 12, 24)
    inp = DecisionInput(
        symbol="SPY",
        strategy=CSP,
        market_regime="NEUTRAL",
        price=100.0,
        price_as_of=now.isoformat(),
        chain_as_of=now.isoformat(),
        contract=OptionContract(delta=-0.25, dte=30, premium=1.5, strike=95.0),
        liquidity_validated_upstream=True,
        sector="ETF",
    )
    pf = PortfolioState(total_value=100_000, available_cash=50_000)
    out = evaluate_candidate(
        inp,
        get_profile("balanced"),
        portfolio=pf,
        now=now,
        as_of_date=today_et,
        macro_provider_configured=True,
        event_calendar=__import__(
            "app.core.environment.event_calendar", fromlist=["DefaultEventCalendar"]
        ).DefaultEventCalendar(),
    )
    assert out.decision_status == "BLOCKED"
    assert "SHORT_SESSION" in out.reason_codes


# ---------------------------------------------------------------------------
# R70-DEF-042 — holidays closed in market_hours
# ---------------------------------------------------------------------------


def test_r70_def042_new_years_day_is_closed() -> None:
    from zoneinfo import ZoneInfo

    from app.market.market_hours import get_market_phase, is_market_open

    et = ZoneInfo("America/New_York")
    # 2026-01-01 15:00 ET would be OPEN under weekday-only logic; must be CLOSED.
    noon_et = datetime(2026, 1, 1, 15, 0, tzinfo=et)
    utc = noon_et.astimezone(ZoneInfo("UTC"))
    assert get_market_phase(utc) == "CLOSED"
    assert is_market_open(utc) is False


def test_r70_def042_regular_weekday_still_open() -> None:
    from zoneinfo import ZoneInfo

    from app.market.market_hours import get_market_phase, is_market_open

    et = ZoneInfo("America/New_York")
    tue = datetime(2026, 1, 6, 12, 0, tzinfo=et)  # regular Tuesday
    utc = tue.astimezone(ZoneInfo("UTC"))
    assert get_market_phase(utc) == "OPEN"
    assert is_market_open(utc) is True


def test_r70_def042_next_open_skips_holiday() -> None:
    from zoneinfo import ZoneInfo

    from app.market.market_hours import get_next_open_close_et

    et = ZoneInfo("America/New_York")
    # New Year's Day 2026 Thursday holiday — next open should be Fri Jan 2.
    nye_morning = datetime(2026, 1, 1, 8, 0, tzinfo=et)
    utc = nye_morning.astimezone(ZoneInfo("UTC"))
    next_open, _ = get_next_open_close_et(utc)
    assert next_open is not None
    assert next_open.startswith("2026-01-02")
