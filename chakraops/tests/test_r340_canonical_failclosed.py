# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — fail-closed canonical live computation (Phase 3).

The live route must NEVER claim canonical authority when the canonical engine
fails or produces no authoritative output, must NOT fall back to a legacy
actionable recommendation, and must return an explicit degraded contract with
empty actionable recommendations and a safe reason code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.server import app
from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
)

CANON = "canonical_decision_engine"
UNAVAIL = "canonical_decision_engine_unavailable"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _artifact(symbols=("AAPL",), *, as_of=None):
    as_of = as_of or _now().isoformat()
    expiration = (_now() + timedelta(days=33)).date().isoformat()
    summaries = [
        SymbolEvalSummary(
            symbol=s, verdict="ELIGIBLE", final_verdict="ELIGIBLE", score=92, band="A",
            primary_reason=None, stage_status="RUN", stage1_status="PASS", stage2_status="PASS",
            provider_status="OK", data_freshness=as_of, evaluated_at=as_of, strategy="CSP",
            price=100.0, expiration=expiration, has_candidates=True, candidate_count=1,
            underlying_price=100.0, expected_credit=200.0,
        )
        for s in symbols
    ]
    selected = [
        CandidateRow(symbol=s, strategy="CSP", expiry=expiration, strike=100.0, delta=0.22,
                     credit_estimate=200.0, max_loss=10000.0)
        for s in symbols
    ]
    return DecisionArtifactV2(
        metadata={"run_id": "failclosed-test", "pipeline_timestamp": as_of},
        symbols=summaries,
        selected_candidates=selected,
        candidates_by_symbol={s: [selected[i]] for i, s in enumerate(symbols)},
        gates_by_symbol={},
        earnings_by_symbol={s: EarningsInfo(earnings_days=30, earnings_block=False, note=None) for s in symbols},
        diagnostics_by_symbol={s: SymbolDiagnosticsDetails(
            technicals={}, exit_plan={}, risk_flags={}, explanation={}, stock={"price": 100.0},
            symbol_eligibility={}, liquidity={"option_liquidity_ok": True}, regime="NEUTRAL",
        ) for s in symbols},
    )


class _FakeStore:
    def __init__(self, artifact):
        self._a = artifact

    def reload_from_disk(self):
        pass

    def get_latest(self):
        return self._a

    def get_symbol(self, sym):
        return None


def _patch_store(monkeypatch, artifact):
    monkeypatch.setattr(
        "app.core.eval.evaluation_store_v2.get_evaluation_store_v2",
        lambda: _FakeStore(artifact),
    )
    monkeypatch.setattr(
        "app.core.eval.evaluation_store_v2.get_eval_snapshot", lambda: {}
    )
    monkeypatch.setattr("app.api.ui_routes._require_ui_key", lambda *a, **k: None)


def _get_action_needed():
    return TestClient(app).get("/api/ui/action-needed").json()


def test_canonical_success_with_seeded_artifact(monkeypatch) -> None:
    _patch_store(monkeypatch, _artifact())
    data = _get_action_needed()
    assert data["decision_source"] == CANON
    assert data["canonical_status"] == "OK"
    assert data["authoritative_recommendations"]["decision_source"] == CANON
    assert data["legacy_lists_role"] == "diagnostic_non_authoritative"


def test_canonical_failure_is_fail_closed(monkeypatch) -> None:
    _patch_store(monkeypatch, _artifact())

    def _boom(*a, **k):
        raise RuntimeError("canonical exploded")

    monkeypatch.setattr(
        "app.core.decision_engine.live_service.compute_live_recommendations", _boom
    )
    data = _get_action_needed()
    # Never claim canonical authority on failure.
    assert data["decision_source"] == UNAVAIL
    assert data["canonical_status"] == "UNAVAILABLE"
    assert data["authoritative_recommendations"]["actionable"] == []
    assert "CANONICAL_ENGINE_UNAVAILABLE" in data["reason_codes"]
    # Legacy lists remain diagnostic, never promoted to primary.
    assert data["legacy_lists_role"] == "diagnostic_non_authoritative"


def test_missing_artifact_is_fail_closed(monkeypatch) -> None:
    _patch_store(monkeypatch, None)
    data = _get_action_needed()
    assert data["decision_source"] == UNAVAIL
    assert data["canonical_status"] == "UNAVAILABLE"
    assert data["authoritative_recommendations"]["actionable"] == []
    assert "CANONICAL_ARTIFACT_MISSING" in data["reason_codes"]


def test_stale_artifact_produces_no_actionable(monkeypatch) -> None:
    stale = (_now() - timedelta(days=6)).isoformat()
    _patch_store(monkeypatch, _artifact(as_of=stale))
    data = _get_action_needed()
    # Canonical still runs and stays authoritative, but no actionable from stale data.
    assert data["decision_source"] == CANON
    assert data["authoritative_recommendations"]["actionable"] == []


def test_no_conflicting_legacy_primary_on_failure(monkeypatch) -> None:
    _patch_store(monkeypatch, _artifact())

    monkeypatch.setattr(
        "app.core.decision_engine.live_service.compute_live_recommendations",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
    )
    data = _get_action_needed()
    # The only authoritative source is canonical; on failure it yields no
    # actionable and legacy is explicitly non-authoritative.
    assert data["decision_source"] == UNAVAIL
    assert data["authoritative_recommendations"]["actionable"] == []
    assert data["legacy_lists_role"] == "diagnostic_non_authoritative"


def test_daily_overview_declares_canonical_source() -> None:
    data = TestClient(app).get("/api/view/daily-overview").json()
    assert data["decision_source"] == CANON
    assert data["view_role"] == "summary_non_authoritative"
    assert "action-needed" in data["authoritative_recommendations_source"]


def test_attach_canonical_decision_fail_closed(monkeypatch) -> None:
    from app.api import ui_routes

    monkeypatch.setattr(
        "app.core.decision_engine.live_service.compute_live_recommendations",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
    )
    out: dict = {}
    ui_routes._attach_canonical_decision(out, _artifact(), "AAPL", "balanced")
    assert out["decision_source"] == UNAVAIL
    assert out["canonical_status"] == "UNAVAILABLE"
    assert out["canonical_decision"] is None
    assert "CANONICAL_ENGINE_UNAVAILABLE" in out["reason_codes"]
