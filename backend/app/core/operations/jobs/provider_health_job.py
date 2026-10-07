# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Provider health check job."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.data.orats_client import probe_orats_live
    from app.core.config.orats_secrets import get_orats_token
    from app.core.security.redact import safe_provider_error
    from app.core.operations.notification_service import notify_orats_unavailable

    if not get_orats_token():
        return {"output_refs": ["token_absent"], "metadata": {"ok": False}}
    try:
        probe_orats_live("SPY")
        return {"output_refs": ["orats_ok"], "metadata": {"ok": True}}
    except Exception as exc:
        msg = safe_provider_error(provider="ORATS", endpoint="probe", detail=exc)
        notify_orats_unavailable(msg)
        raise


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="provider_health",
            purpose="ORATS provider health probe",
            owner="operations",
            schedule_cron="Every 30m America/New_York",
            timezone="America/New_York",
            lock_name="job_provider_health",
            timeout_seconds=60.0,
            max_retries=0,
            retry_base_seconds=10.0,
            retry_max_seconds=60.0,
            notification_policy="CRITICAL",
            failure_classification="provider_unavailable",
            manual_command="GET /api/data-health",
            recovery_procedure="Verify ORATS token and network; wait for provider recovery",
            enabled_env_var="CHAKRAOPS_JOB_PROVIDER_HEALTH_ENABLED",
        ),
        _run,
    )
