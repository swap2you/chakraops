# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Scheduled weekly universe refresh job."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.universe.weekly_refresh import apply_weekly_universe_refresh

    result = apply_weekly_universe_refresh(as_of=date.today())
    return {
        "output_refs": [result.get("status", "unknown")],
        "metadata": result,
    }


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="weekly_universe_refresh",
            purpose="Apply transaction-safe weekly universe refresh",
            owner="operations",
            schedule_cron="Sun 06:00 America/New_York",
            timezone="America/New_York",
            lock_name="job_weekly_universe_refresh",
            timeout_seconds=600.0,
            max_retries=1,
            retry_base_seconds=30.0,
            retry_max_seconds=120.0,
            notification_policy="CRITICAL",
            failure_classification="data_integrity",
            manual_command="python -c \"from app.core.operations.job_executor import execute_job; ...\"",
            recovery_procedure="Inspect refresh journal; run recover_pending_transaction; retry manual apply",
            input_dependencies=["universe_manifest", "refresh_history"],
            freshness_requirements=["ORATS delayed/live for manifest symbols"],
            output_artifacts=["universe_overlay", "refresh_history.jsonl"],
            enabled_env_var="CHAKRAOPS_JOB_WEEKLY_UNIVERSE_REFRESH_ENABLED",
        ),
        _run,
    )
