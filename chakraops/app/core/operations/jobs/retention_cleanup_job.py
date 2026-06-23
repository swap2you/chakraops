# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Retention and archive cleanup job."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.operations.backup_service import cleanup_expired_backups

    result = cleanup_expired_backups(retain_count=10)
    return {"output_refs": result.get("removed") or [], "metadata": result}


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="retention_cleanup",
            purpose="Expire old backups and enforce retention policy",
            owner="operations",
            schedule_cron="Sun 03:00 America/New_York",
            timezone="America/New_York",
            lock_name="job_retention_cleanup",
            timeout_seconds=300.0,
            max_retries=0,
            retry_base_seconds=10.0,
            retry_max_seconds=60.0,
            notification_policy="WARNING",
            failure_classification="retention",
            manual_command="scripts/cleanup_expired_backups.ps1",
            recovery_procedure="Inspect disk; adjust retain_count; rerun manually",
            enabled_env_var="CHAKRAOPS_JOB_RETENTION_CLEANUP_ENABLED",
        ),
        _run,
    )
