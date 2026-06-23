# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""EOD data refresh job — after market-close buffer."""

from __future__ import annotations

from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.eval.eod_chain_snapshot import run_eod_chain_snapshot_job
    from app.core.security.redact import safe_provider_error
    from app.core.operations.notification_service import notify_orats_unavailable

    result = run_eod_chain_snapshot_job()
    if result.get("skipped"):
        return {"output_refs": [result.get("reason", "skipped")], "metadata": result}
    if result.get("errors", 0) > 0 and result.get("written", 0) == 0:
        msg = safe_provider_error(provider="ORATS", endpoint="eod_chain", detail="all symbols failed")
        notify_orats_unavailable(msg)
        raise RuntimeError(msg)
    return {"output_refs": [f"written={result.get('written', 0)}"], "metadata": result}


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="eod_data_refresh",
            purpose="EOD ORATS chain snapshot after market-close buffer",
            owner="operations",
            schedule_cron="Mon-Fri 16:10 America/New_York",
            timezone="America/New_York",
            lock_name="job_eod_data_refresh",
            timeout_seconds=1800.0,
            max_retries=1,
            retry_base_seconds=60.0,
            retry_max_seconds=300.0,
            notification_policy="CRITICAL",
            failure_classification="provider_unavailable",
            manual_command="POST /api/operations/jobs/eod_data_refresh/run",
            recovery_procedure="Verify ORATS health; retry after provider recovery",
            input_dependencies=["universe_symbols", "ORATS credentials present"],
            freshness_requirements=["market closed + buffer elapsed"],
            output_artifacts=["eod_chain_snapshots"],
            enabled_env_var="CHAKRAOPS_JOB_EOD_DATA_REFRESH_ENABLED",
        ),
        _run,
    )
