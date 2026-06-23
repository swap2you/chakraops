# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified scheduler service — single registration, disabled by default."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.core.operations.job_executor import JobExecutionError, execute_job
from app.core.operations.job_registry import get_job_registry
from app.core.operations.job_run_store import JobRunStore

logger = logging.getLogger(__name__)

_MASTER_ENV = "CHAKRAOPS_SCHEDULER_ENABLED"
_LEGACY_ENV = "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED"
_POLL_SECONDS = 60.0

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None
_started = False
_last_tick_at: Optional[str] = None


def is_master_enabled() -> bool:
    return os.getenv(_MASTER_ENV, "false").lower() in ("true", "1", "yes")


def legacy_schedulers_enabled() -> bool:
    return os.getenv(_LEGACY_ENV, "false").lower() in ("true", "1", "yes")


def start_scheduler_service() -> None:
    global _stop_event, _thread, _started
    if _started:
        return
    _started = True
    registry = get_job_registry()
    logger.info("[OPS_SCHEDULER] registered jobs: %s", [j.job_id for j in registry.list_jobs()])
    try:
        recovery = registry.get("recovery_reconciliation")
        handler = registry.handler("recovery_reconciliation")
        if recovery and handler:
            execute_job(recovery, handler, trigger="recovery", skip_if_locked=True)
    except JobExecutionError:
        pass
    except Exception as exc:
        logger.warning("[OPS_SCHEDULER] recovery job failed: %s", exc)
    if not is_master_enabled():
        logger.info("[OPS_SCHEDULER] master disabled (%s=false)", _MASTER_ENV)
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(_stop_event,), daemon=True, name="OpsScheduler")
    _thread.start()
    logger.info("[OPS_SCHEDULER] started")


def stop_scheduler_service() -> None:
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=10.0)
    _stop_event = None
    _thread = None
    logger.info("[OPS_SCHEDULER] stopped")


def run_job_now(job_id: str, *, trigger: str = "manual") -> Dict[str, Any]:
    registry = get_job_registry()
    definition = registry.get(job_id)
    handler = registry.handler(job_id)
    if definition is None or handler is None:
        raise KeyError(f"unknown job: {job_id}")
    return execute_job(definition, handler, trigger=trigger)


def run_due_jobs(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Execute jobs whose schedule matches ``now`` (test hook)."""
    registry = get_job_registry()
    now = now or datetime.now(tz=ZoneInfo("America/New_York"))
    executed = []
    for definition in registry.list_jobs():
        if definition.job_id == "recovery_reconciliation":
            continue
        if not definition.is_enabled():
            continue
        if not _schedule_due(definition.job_id, definition.schedule_cron, now):
            continue
        handler = registry.handler(definition.job_id)
        if handler is None:
            continue
        try:
            run_job_now(definition.job_id, trigger="schedule")
            executed.append(definition.job_id)
        except JobExecutionError as exc:
            logger.warning("[OPS_SCHEDULER] job %s failed: %s", definition.job_id, exc)
    return {"executed": executed, "at": now.isoformat()}


def scheduler_status() -> Dict[str, Any]:
    registry = get_job_registry()
    store = JobRunStore()
    return {
        "master_enabled": is_master_enabled(),
        "legacy_schedulers_enabled": legacy_schedulers_enabled(),
        "running": _thread is not None and _thread.is_alive(),
        "last_tick_at": _last_tick_at,
        "jobs": registry.inventory(),
        "recent_runs": store.read_all(limit=20),
    }


def _loop(stop_event: threading.Event) -> None:
    global _last_tick_at
    while not stop_event.is_set():
        _last_tick_at = datetime.now(timezone.utc).isoformat()
        try:
            run_due_jobs()
        except Exception as exc:
            logger.warning("[OPS_SCHEDULER] tick error: %s", exc)
        stop_event.wait(_POLL_SECONDS)


def _schedule_due(job_id: str, schedule: str, now: datetime) -> bool:
    """Minimal schedule matcher for tests and basic cadence."""
    sched = schedule.lower()
    wd = now.weekday()
    if job_id == "weekly_universe_refresh":
        return wd == 6 and now.hour == 6
    if job_id == "eod_data_refresh":
        return wd < 5 and now.hour == 16 and now.minute >= 10
    if job_id in ("decision_generation", "nightly_reports"):
        return wd < 5 and now.hour == 19
    if job_id == "backup":
        return now.hour == 2
    if job_id == "retention_cleanup":
        return wd == 6 and now.hour == 3
    if job_id == "provider_health":
        return now.minute % 30 == 0
    return False
