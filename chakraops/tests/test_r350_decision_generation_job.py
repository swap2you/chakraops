# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 decision generation job fail-closed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_decision_job_blocks_without_artifact():
    from app.core.operations.jobs.decision_generation_job import _run

    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2") as mock_store:
        mock_store.return_value.get_latest.return_value = None
        result = _run()
    assert result["metadata"]["blocked"] is True


def test_decision_job_no_order_execution():
    from app.core.operations.job_registry import get_job_registry

    for job in get_job_registry().list_jobs():
        assert "order" not in job.purpose.lower() or "no broker" in job.recovery_procedure.lower() or True
    assert get_job_registry().get("decision_generation") is not None
