# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Recovery job for interrupted STARTED runs."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.operations.job_run_store import JobRunStore
    from app.core.operations.notification_service import notify_job_recovery

    store = JobRunStore()
    # Never recover our own in-flight STARTED row (execute_job starts recovery first),
    # and ignore very young STARTED rows to avoid racing concurrent jobs.
    interrupted = store.interrupted_started_runs(
        exclude_job_ids={"recovery_reconciliation"},
        min_age_seconds=15.0,
    )
    recovered = []
    for rec in interrupted:
        store.mark_recovered(rec["run_id"], "marked recovered on startup")
        job_id = str(rec.get("job_id") or "unknown")
        # Do not emit recovery noise for the recovery job itself.
        if job_id != "recovery_reconciliation":
            notify_job_recovery(job_id, "interrupted run cleared")
        recovered.append(rec["run_id"])
    return {"output_refs": recovered, "metadata": {"count": len(recovered)}}


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="recovery_reconciliation",
            purpose="Detect and reconcile interrupted STARTED job runs",
            owner="operations",
            schedule_cron="On startup",
            timezone="America/New_York",
            lock_name="job_recovery",
            timeout_seconds=120.0,
            max_retries=0,
            retry_base_seconds=5.0,
            retry_max_seconds=30.0,
            notification_policy="INFO",
            failure_classification="recovery",
            manual_command="POST /api/operations/jobs/recovery_reconciliation/run",
            recovery_procedure="Review job_runs.jsonl; rerun failed jobs manually",
            enabled_env_var="CHAKRAOPS_JOB_RECOVERY_RECONCILIATION_ENABLED",
        ),
        _run,
    )
