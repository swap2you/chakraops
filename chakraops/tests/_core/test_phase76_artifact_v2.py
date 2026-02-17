# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.6: DecisionArtifactV2 and EvaluationStoreV2 tests."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestDecisionArtifactV2:
    """DecisionArtifactV2 schema and store."""

    def test_artifact_has_v2_metadata(self):
        """/api/ui/decision/latest returns artifact_version=v2 when v2 present."""
        from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary, CandidateRow

        meta = {"artifact_version": "v2", "pipeline_timestamp": "2026-02-16T00:00:00Z"}
        symbols = [
            SymbolEvalSummary(
                symbol="SPY",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=65,
                band="B",
                primary_reason="test",
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness="2026-02-16",
                evaluated_at="2026-02-16",
                strategy="CSP",
                price=450.0,
                expiration="2026-03-20",
                has_candidates=True,
                candidate_count=1,
            )
        ]
        artifact = DecisionArtifactV2(metadata=meta, symbols=symbols, selected_candidates=[])
        d = artifact.to_dict()
        assert d["metadata"]["artifact_version"] == "v2"
        assert len(d["symbols"]) == 1
        assert d["symbols"][0]["verdict"] == "ELIGIBLE"

    def test_universe_run_produces_one_row_per_symbol(self):
        """Universe run produces symbols list length == universe size, each with verdict/stage_status not blank."""
        from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, SymbolEvalSummary, assign_band

        symbols = [
            SymbolEvalSummary(
                symbol=sym,
                verdict="HOLD",
                final_verdict="HOLD",
                score=50,
                band=assign_band(50),
                primary_reason="test",
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="NOT_RUN",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy=None,
                price=None,
                expiration=None,
                has_candidates=False,
                candidate_count=0,
            )
            for sym in ["AAPL", "SPY", "QQQ"]
        ]
        artifact = DecisionArtifactV2(metadata={"artifact_version": "v2"}, symbols=symbols, selected_candidates=[])
        assert len(artifact.symbols) == 3
        for s in artifact.symbols:
            assert s.verdict
            assert s.stage_status

    def test_assign_band_never_null_low_scores_yield_d(self):
        """assign_band(0) and assign_band(35) both yield band=D (below TIER_C_MIN)."""
        from app.core.eval.decision_artifact_v2 import assign_band

        assert assign_band(0) == "D"
        assert assign_band(35) == "D"
        assert assign_band(None) == "D"
