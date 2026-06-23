# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Job handlers for the R35.0 operations scheduler."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def register_all_jobs(registry: JobRegistry) -> None:
    from app.core.operations.jobs.backup_job import register as reg_backup
    from app.core.operations.jobs.decision_generation_job import register as reg_decision
    from app.core.operations.jobs.eod_data_refresh_job import register as reg_eod
    from app.core.operations.jobs.nightly_reports_job import register as reg_reports
    from app.core.operations.jobs.provider_health_job import register as reg_health
    from app.core.operations.jobs.recovery_job import register as reg_recovery
    from app.core.operations.jobs.retention_cleanup_job import register as reg_retention
    from app.core.operations.jobs.weekly_refresh_job import register as reg_weekly

    for reg in (
        reg_weekly,
        reg_eod,
        reg_decision,
        reg_reports,
        reg_backup,
        reg_health,
        reg_retention,
        reg_recovery,
    ):
        reg(registry)
