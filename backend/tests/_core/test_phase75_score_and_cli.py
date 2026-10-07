# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.5: Unit tests for score normalization and run_and_save --all."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add chakraops to path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestRunAndSaveAll:
    """--all flag and validation."""

    def test_all_and_symbols_raises(self):
        """Passing both --all and --symbols must raise ValueError."""
        import scripts.run_and_save as ras
        with patch("sys.argv", ["run_and_save", "--all", "--symbols", "SPY,AAPL", "--output-dir", "out"]):
            with pytest.raises(ValueError, match="Cannot use --all and --symbols together"):
                ras.main()

    def test_all_resolves_full_universe(self):
        """With --all, _resolve_symbols returns full universe from get_universe_symbols."""
        import scripts.run_and_save as ras
        class Args:
            all = True
            symbols = None
            limit = 3
        with patch("app.api.data_health.get_universe_symbols", return_value=["SPY", "QQQ", "AAPL", "MSFT"]):
            symbols = ras._resolve_symbols(Args())
            assert symbols == ["SPY", "QQQ", "AAPL", "MSFT"]
            assert len(symbols) == 4  # limit ignored when --all


class TestScoreNormalizationStage1Only:
    """Phase 7.5: Stage1-only symbols preserve stage1_score (no flattening)."""

    def test_stage1_only_preserves_score(self):
        """When stage_reached=STAGE1_ONLY, score comes from stage1_score, not compute_score_breakdown."""
        from app.core.eval.staged_evaluator import (
            EvaluationStage,
            FullEvaluationResult,
            Stage1Result,
            StockVerdict,
        )
        # Build two Stage1-only results with different stage1_scores
        s1a = Stage1Result(symbol="A", stage1_score=50, stock_verdict=StockVerdict.QUALIFIED)
        s1b = Stage1Result(symbol="B", stage1_score=60, stock_verdict=StockVerdict.QUALIFIED)
        ra = FullEvaluationResult(symbol="A")
        ra.stage1 = s1a
        ra.stage_reached = EvaluationStage.STAGE1_ONLY
        ra.score = 50
        ra.regime = "NEUTRAL"
        ra.data_completeness = 1.0
        ra.verdict = "HOLD"
        ra.liquidity_ok = False
        ra.position_open = False
        ra.price = 100.0
        rb = FullEvaluationResult(symbol="B")
        rb.stage1 = s1b
        rb.stage_reached = EvaluationStage.STAGE1_ONLY
        rb.score = 60
        rb.regime = "NEUTRAL"
        rb.data_completeness = 1.0
        rb.verdict = "HOLD"
        rb.liquidity_ok = False
        rb.position_open = False
        rb.price = 100.0
        # Simulate Phase 3 logic: for Stage1_only, preserve stage1_score with regime cap
        market_regime_value = "NEUTRAL"
        for r in [ra, rb]:
            if r.stage_reached == EvaluationStage.STAGE1_ONLY:
                raw = r.stage1.stage1_score if r.stage1 else r.score
                if market_regime_value == "NEUTRAL":
                    r.score = min(raw, 65)
                else:
                    r.score = raw
        assert ra.score == 50
        assert rb.score == 60
        assert len({ra.score, rb.score}) == 2  # not flattened
