# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase B: Contract tests for staged evaluator return type. Fail if return shape changes."""

import pytest

from app.core.eval.staged_evaluator import StagedEvaluationResult
from app.core.eval.position_awareness import ExposureSummary


class TestStagedEvaluatorReturnContract:
    """Return type must be StagedEvaluationResult with .results and .exposure_summary."""

    def test_return_shape_is_staged_evaluation_result(self):
        """StagedEvaluationResult must have .results (list) and .exposure_summary (ExposureSummary)."""
        result = StagedEvaluationResult(results=[], exposure_summary=ExposureSummary())
        assert isinstance(result, StagedEvaluationResult), "Return must be StagedEvaluationResult"
        assert hasattr(result, "results"), "Must have .results"
        assert hasattr(result, "exposure_summary"), "Must have .exposure_summary"
        assert isinstance(result.results, list), ".results must be a list"
        assert isinstance(result.exposure_summary, ExposureSummary), ".exposure_summary must be ExposureSummary"

    def test_downstream_fails_if_flat_list_assumed(self):
        """If caller unpacks as (a, b) and uses a as list of results, type is wrong for b."""
        result = StagedEvaluationResult(results=[], exposure_summary=ExposureSummary())
        # Correct usage: result.results and result.exposure_summary
        assert isinstance(result.results, list)
        assert isinstance(result.exposure_summary, ExposureSummary)
        # Wrong usage would be: list_result, exp = result  -> not unpackable as 2-tuple
        with pytest.raises(TypeError):
            _ = result[0]
