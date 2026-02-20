# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.7: Eval determinism — Universe eval and per-symbol recompute use same pipeline; same inputs → same output."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

TEST_SYMBOL = "NKE"


def _make_mock_staged_result():
    """Build a minimal UniverseEvaluationResult with one symbol for deterministic comparison."""
    from app.core.eval.universe_evaluator import UniverseEvaluationResult, SymbolEvaluationResult

    sr = SymbolEvaluationResult(
        symbol=TEST_SYMBOL,
        verdict="ELIGIBLE",
        primary_reason="Stock qualified (score: 55)",
        score=55,
        regime="BULL",
        liquidity_ok=True,
        options_available=True,
        stage_reached="STAGE2_CHAIN",
        candidate_trades=[],
        gates=[],
        blockers=[],
        fetched_at="2026-02-17T12:00:00Z",
        quote_date="2026-02-17",
        symbol_eligibility={"status": "PASS", "reasons": []},
    )
    return UniverseEvaluationResult(
        evaluation_state="COMPLETED",
        total=1,
        evaluated=1,
        eligible=1,
        symbols=[sr],
        alerts=[],
        errors=[],
        engine="staged",
    )


def test_universe_eval_and_recompute_same_core_same_output(tmp_path: Path) -> None:
    """
    R22.7: When both paths get the same staged result (same inputs), artifact symbol row must be identical.
    Mocks run_universe_evaluation_staged so both evaluate_universe([SYM]) and evaluate_single_symbol_and_merge(SYM)
    see the same deterministic result; asserts score, band, verdict, primary_reason_codes match.
    """
    from app.core.eval.evaluation_service_v2 import evaluate_universe, evaluate_single_symbol_and_merge
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    set_output_dir(tmp_path)
    mock_result = _make_mock_staged_result()

    try:
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            artifact_universe = evaluate_universe([TEST_SYMBOL], mode="LIVE")
        row_universe = next((s for s in artifact_universe.symbols if (s.symbol or "").strip().upper() == TEST_SYMBOL), None)
        assert row_universe is not None, "Symbol from universe eval must be present"

        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            artifact_recompute = evaluate_single_symbol_and_merge(symbol=TEST_SYMBOL, mode="LIVE")
        row_recompute = next((s for s in artifact_recompute.symbols if (s.symbol or "").strip().upper() == TEST_SYMBOL), None)
        assert row_recompute is not None, "Symbol from recompute merge must be present"

        assert row_recompute.score == row_universe.score, "Score must match (determinism)"
        assert row_recompute.band == row_universe.band, "Band must match (determinism)"
        assert row_recompute.verdict == row_universe.verdict, "Verdict must match (determinism)"
        assert (row_recompute.primary_reason_codes or []) == (row_universe.primary_reason_codes or []), (
            "primary_reason_codes must match (determinism)"
        )
    finally:
        reset_output_dir()
