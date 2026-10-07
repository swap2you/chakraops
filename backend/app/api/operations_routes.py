# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Operations dashboard API (R35.0)."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/operations", tags=["operations"])

_CONFIRM_TOKEN = "ENABLE"


def _git_commit() -> Optional[str]:
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip()
    except Exception:
        return None


@router.get("/status")
def operations_status() -> Dict[str, Any]:
    from app.core.operations.scheduler_service import scheduler_status
    from app.core.operations.backup_service import list_backups
    from app.core.config.orats_secrets import get_orats_token

    status = scheduler_status()
    backups = list_backups()
    latest_backup = backups[0] if backups else None
    return {
        "application_version": "0.1.0",
        "commit": _git_commit(),
        "scheduler": status,
        "orats_token_present": bool(get_orats_token()),
        "backup": {
            "latest": latest_backup,
            "count": len(backups),
        },
        "manual_only": True,
        "trade_execution": False,
    }


@router.get("/jobs")
def list_jobs() -> Dict[str, Any]:
    from app.core.operations.job_registry import get_job_registry

    registry = get_job_registry()
    return {"jobs": registry.inventory()}


@router.get("/jobs/{job_id}/runs")
def job_runs(job_id: str, limit: int = Query(20, ge=1, le=200)) -> Dict[str, Any]:
    from app.core.operations.job_run_store import JobRunStore

    return {"job_id": job_id, "runs": JobRunStore().recent_for_job(job_id, limit=limit)}


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str) -> Dict[str, Any]:
    from app.core.operations.scheduler_service import run_job_now
    from app.core.operations.job_executor import JobExecutionError

    try:
        return run_job_now(job_id, trigger="manual")
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown job")
    except JobExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/scheduler/enable")
def enable_scheduler(confirm: str = Query(...)) -> Dict[str, Any]:
    if confirm != _CONFIRM_TOKEN:
        raise HTTPException(status_code=400, detail="confirmation required: confirm=ENABLE")
    os.environ["CHAKRAOPS_SCHEDULER_ENABLED"] = "true"
    from app.core.operations.scheduler_service import start_scheduler_service

    start_scheduler_service()
    return {"enabled": True, "message": "Scheduler enabled; individual jobs still require per-job env vars"}


@router.post("/scheduler/disable")
def disable_scheduler() -> Dict[str, Any]:
    os.environ["CHAKRAOPS_SCHEDULER_ENABLED"] = "false"
    from app.core.operations.scheduler_service import stop_scheduler_service

    stop_scheduler_service()
    return {"enabled": False}


@router.post("/jobs/{job_id}/enable")
def enable_job(job_id: str, confirm: str = Query(...)) -> Dict[str, Any]:
    if confirm != _CONFIRM_TOKEN:
        raise HTTPException(status_code=400, detail="confirmation required: confirm=ENABLE")
    from app.core.operations.job_registry import get_job_registry

    definition = get_job_registry().get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="unknown job")
    var = definition.enabled_env_var or f"CHAKRAOPS_JOB_{job_id.upper()}_ENABLED"
    os.environ[var] = "true"
    return {"job_id": job_id, "enabled": True, "env_var": var}


@router.post("/jobs/{job_id}/disable")
def disable_job(job_id: str) -> Dict[str, Any]:
    from app.core.operations.job_registry import get_job_registry

    definition = get_job_registry().get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="unknown job")
    var = definition.enabled_env_var or f"CHAKRAOPS_JOB_{job_id.upper()}_ENABLED"
    os.environ[var] = "false"
    return {"job_id": job_id, "enabled": False, "env_var": var}


@router.get("/backups")
def list_backup_manifests() -> Dict[str, Any]:
    from app.core.operations.backup_service import list_backups

    return {"backups": list_backups()}


@router.post("/backups/create")
def create_backup_now() -> Dict[str, Any]:
    from app.core.operations.backup_service import create_backup, verify_backup

    created = create_backup(label="manual")
    verify = verify_backup(created["backup_id"])
    return {"created": created, "verify": verify}
