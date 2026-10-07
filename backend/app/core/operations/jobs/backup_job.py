# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Backup job."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.operations.backup_service import create_backup, verify_backup

    created = create_backup(label="scheduled")
    verify = verify_backup(created["backup_id"])
    return {
        "output_refs": [created["backup_id"]],
        "metadata": {"verify_ok": verify.get("ok"), **created},
    }


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="backup",
            purpose="SQLite + JSONL backup with manifest verification",
            owner="operations",
            schedule_cron="Daily 02:00 America/New_York",
            timezone="America/New_York",
            lock_name="job_backup",
            timeout_seconds=600.0,
            max_retries=1,
            retry_base_seconds=30.0,
            retry_max_seconds=120.0,
            notification_policy="CRITICAL",
            failure_classification="backup_failure",
            manual_command="scripts/backup_chakraops.ps1",
            recovery_procedure="Inspect disk space; rerun backup; verify manifest",
            output_artifacts=["out/backups/*"],
            enabled_env_var="CHAKRAOPS_JOB_BACKUP_ENABLED",
        ),
        _run,
    )
