# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Nightly reports job."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.eval.nightly_evaluation import run_nightly_evaluation

    result = run_nightly_evaluation()
    return {
        "output_refs": [result.get("run_id") or "nightly"],
        "metadata": result,
    }


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="nightly_reports",
            purpose="Nightly decision summary and portfolio exposure reports",
            owner="operations",
            schedule_cron="Mon-Fri 19:30 America/New_York",
            timezone="America/New_York",
            lock_name="job_nightly_reports",
            timeout_seconds=1200.0,
            max_retries=1,
            retry_base_seconds=60.0,
            retry_max_seconds=180.0,
            notification_policy="WARNING",
            failure_classification="report_failure",
            manual_command="POST /api/operations/jobs/nightly_reports/run",
            recovery_procedure="Check eval store; rerun nightly evaluation manually",
            output_artifacts=["nightly_eval_artifact", "reports"],
            enabled_env_var="CHAKRAOPS_JOB_NIGHTLY_REPORTS_ENABLED",
        ),
        _run,
    )
