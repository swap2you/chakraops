# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.7: Earnings advisory correctness — no EARNINGS_NOT_EVALUATED in decision artifact; determinism."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eval.decision_artifact_v2 import (
    DecisionArtifactV2,
    EarningsInfo,
    SymbolEvalSummary,
)
from app.core.eval.evaluation_service_v2 import evaluate_universe
from app.core.eval.evaluation_store_v2 import (
    get_decision_store_path,
    get_eval_snapshot,
    get_evaluation_store_v2,
    set_output_dir,
    reset_output_dir,
)


def test_earnings_persist_never_contains_earnings_not_evaluated() -> None:
    """R25.7: to_dict_persist() must never output status_code EARNINGS_NOT_EVALUATED."""
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "run_id": "r257-test"},
        symbols=[
            SymbolEvalSummary(
                symbol="T1",
                verdict="HOLD",
                final_verdict="HOLD",
                score=50,
                band="C",
                primary_reason=None,
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="NOT_RUN",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy=None,
                price=100.0,
                expiration=None,
                has_candidates=False,
                candidate_count=0,
            ),
        ],
        selected_candidates=[],
        candidates_by_symbol={},
        gates_by_symbol={},
        earnings_by_symbol={
            "T1": EarningsInfo(None, None, "Not evaluated", status_code="EARNINGS_NOT_EVALUATED"),
        },
        diagnostics_by_symbol={},
        warnings=[],
    )
    d = artifact.to_dict_persist()
    eb = d.get("earnings_by_symbol") or {}
    for sym, e in eb.items():
        sc = e.get("status_code")
        assert sc != "EARNINGS_NOT_EVALUATED", f"R25.7: {sym} must not persist EARNINGS_NOT_EVALUATED, got {sc}"
        assert sc in ("OK", "Unavailable", "Stale", "EARNINGS_BLOCKED"), f"R25.7: status must be safe, got {sc}"


def test_earnings_persist_safe_statuses_only() -> None:
    """R25.7: Only OK, Unavailable, Stale, EARNINGS_BLOCKED in persisted earnings."""
    for status in ("OK", "Unavailable", "Stale", "EARNINGS_BLOCKED"):
        artifact = DecisionArtifactV2(
            metadata={"artifact_version": "v2"},
            symbols=[],
            selected_candidates=[],
            candidates_by_symbol={},
            gates_by_symbol={},
            earnings_by_symbol={
                "S": EarningsInfo(10, False, None, status_code=status),
            },
            diagnostics_by_symbol={},
            warnings=[],
        )
        d = artifact.to_dict_persist()
        sc = (d.get("earnings_by_symbol") or {}).get("S", {}).get("status_code")
        assert sc in ("OK", "Unavailable", "Stale", "EARNINGS_BLOCKED"), f"status {status} persisted as {sc}"


def test_eval_universe_earnings_no_not_evaluated(tmp_path: Path) -> None:
    """R25.7: After evaluate_universe (with mocked advisory), decision_latest has no EARNINGS_NOT_EVALUATED."""
    set_output_dir(tmp_path)
    get_decision_store_path().parent.mkdir(parents=True, exist_ok=True)

    mock_adv = {
        "AAPL": {
            "earnings_days": 14,
            "earnings_next_date": "2026-03-15",
            "earnings_data_status": "OK",
            "implied_earnings_move_pct": 7.2,
            "earnings_annc_tod": "AMC",
            "earnings_as_of": "2026-02-27T12:00:00Z",
        },
        "MSFT": {
            "earnings_days": None,
            "earnings_next_date": None,
            "earnings_data_status": "Unavailable",
            "implied_earnings_move_pct": None,
            "earnings_annc_tod": "Unknown",
            "earnings_as_of": "2026-02-27T12:00:00Z",
        },
    }

    class StagedResult:
        symbol = "AAPL"
        verdict = "HOLD"
        score = 50
        stage_reached = type("Stage", (), {"value": "STAGE1_ONLY"})()
        liquidity_ok = False
        earnings_blocked = False
        earnings_days = None
        candidate_trades = []
        gates = [{"name": "Earnings Check", "status": "PASS"}]
        price = 100.0
        primary_reason = "HOLD"
        quote_date = None
        data_completeness = 0.9
        missing_fields = []
        selected_contract = None
        selected_expiration = None
        score_breakdown = None
        band_reason = None
        regime = "NEUTRAL"
        eligibility_trace = {}
        stage2_trace = None
        liquidity_gates = {}
        symbol_eligibility = {}
        stage2 = None
        capital_hint = None
        market_cap = None
        top_rejection_reasons = {}

    try:
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged") as run_staged:
            run_staged.return_value = type("Result", (), {"symbols": [StagedResult()]})()
            with patch("app.core.orats.earnings.fetch_earnings_advisory_batch", return_value=mock_adv):
                with patch("app.core.config.orats_secrets.ORATS_API_TOKEN", "test"):
                    art = evaluate_universe(["AAPL"], mode="LIVE")
        assert art is not None
        path = get_decision_store_path()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        eb = data.get("earnings_by_symbol") or {}
        for sym, e in eb.items():
            sc = e.get("status_code")
            assert sc != "EARNINGS_NOT_EVALUATED", f"R25.7: {sym} has EARNINGS_NOT_EVALUATED in decision_latest"
            assert sc in ("OK", "Unavailable", "Stale", "EARNINGS_BLOCKED")
        raw = path.read_text(encoding="utf-8")
        assert "EARNINGS_NOT_EVALUATED" not in raw
        assert "FAIL_" not in raw
        assert "WARN_" not in raw
    finally:
        reset_output_dir()


def test_decision_latest_json_no_forbidden_earnings_codes() -> None:
    """R25.7: Persisted earnings_by_symbol never contains EARNINGS_NOT_EVALUATED; payload has no FAIL_/WARN_."""
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2"},
        symbols=[],
        selected_candidates=[],
        candidates_by_symbol={},
        gates_by_symbol={},
        earnings_by_symbol={
            "X": EarningsInfo(5, False, None, status_code="OK"),
            "Y": EarningsInfo(None, False, "Not evaluated", status_code=None),
        },
        diagnostics_by_symbol={},
        warnings=[],
    )
    d = artifact.to_dict_persist()
    raw = json.dumps(d, default=str)
    assert "EARNINGS_NOT_EVALUATED" not in raw
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
    eb = d.get("earnings_by_symbol") or {}
    assert eb.get("Y", {}).get("status_code") == "Unavailable"
