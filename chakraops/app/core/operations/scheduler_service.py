# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified scheduler service — single registration, disabled by default."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.core.operations.job_executor import JobExecutionError, execute_job
from app.core.operations.job_registry import get_job_registry
from app.core.operations.job_run_store import JobRunStore
from app.core.operations.occurrence_store import (
    MISSED_RUN_POLICY,
    is_completed,
    mark_completed,
    occurrence_key,
)

logger = logging.getLogger(__name__)

_MASTER_ENV = "CHAKRAOPS_SCHEDULER_ENABLED"
_LEGACY_ENV = "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED"
_POLL_SECONDS = 60.0

_lifecycle_lock = threading.Lock()
_stop_event: Optional[threading.Event] = None
_poll_thread: Optional[threading.Thread] = None
_recovery_done = False
_last_tick_at: Optional[str] = None
_start_failed = False


def is_master_enabled() -> bool:
    return os.getenv(_MASTER_ENV, "false").lower() in ("true", "1", "yes")


def legacy_schedulers_enabled() -> bool:
    return os.getenv(_LEGACY_ENV, "false").lower() in ("true", "1", "yes")


def _run_recovery() -> None:
    registry = get_job_registry()
    try:
        recovery = registry.get("recovery_reconciliation")
        handler = registry.handler("recovery_reconciliation")
        if recovery and handler:
            execute_job(recovery, handler, trigger="recovery", skip_if_locked=True)
    except JobExecutionError:
        pass
    except Exception as exc:
        logger.warning("[OPS_SCHEDULER] recovery job failed: %s", exc)


def _ensure_poll_thread() -> bool:
    """Start poll thread if not running. Returns True when thread is alive."""
    global _stop_event, _poll_thread, _start_failed
    if _poll_thread is not None and _poll_thread.is_alive():
        return True
    try:
        _stop_event = threading.Event()
        _poll_thread = threading.Thread(
            target=_loop, args=(_stop_event,), daemon=True, name="OpsScheduler"
        )
        _poll_thread.start()
        _start_failed = False
        logger.info("[OPS_SCHEDULER] poll thread started")
        return True
    except Exception as exc:
        _stop_event = None
        _poll_thread = None
        _start_failed = True
        logger.error("[OPS_SCHEDULER] failed to start poll thread: %s", exc)
        return False


def start_scheduler_service() -> None:
    """Idempotent startup: recovery once; poll thread only when master enabled."""
    global _recovery_done
    registry = get_job_registry()
    with _lifecycle_lock:
        if not _recovery_done:
            logger.info(
                "[OPS_SCHEDULER] registered jobs: %s",
                [j.job_id for j in registry.list_jobs()],
            )
            _run_recovery()
            _recovery_done = True
        if not is_master_enabled():
            logger.info("[OPS_SCHEDULER] master disabled (%s=false)", _MASTER_ENV)
            return
        _ensure_poll_thread()


def stop_scheduler_service() -> None:
    """Stop poll thread and reset lifecycle so restart works."""
    global _stop_event, _poll_thread, _start_failed
    with _lifecycle_lock:
        if _stop_event is not None:
            _stop_event.set()
        if _poll_thread is not None and _poll_thread.is_alive():
            _poll_thread.join(timeout=10.0)
        _stop_event = None
        _poll_thread = None
        _start_failed = False
        logger.info("[OPS_SCHEDULER] stopped")


def run_job_now(job_id: str, *, trigger: str = "manual") -> Dict[str, Any]:
    registry = get_job_registry()
    definition = registry.get(job_id)
    handler = registry.handler(job_id)
    if definition is None or handler is None:
        raise KeyError(f"unknown job: {job_id}")
    return execute_job(definition, handler, trigger=trigger)


def run_due_jobs(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Execute jobs whose schedule matches ``now`` at most once per occurrence."""
    registry = get_job_registry()
    now = now or datetime.now(tz=ZoneInfo("America/New_York"))
    executed = []
    skipped_occurrence = []
    for definition in registry.list_jobs():
        if definition.job_id == "recovery_reconciliation":
            continue
        if not definition.is_enabled():
            continue
        if not _schedule_due(definition.job_id, definition.schedule_cron, now):
            continue
        occ_key = occurrence_key(definition.job_id, now)
        if is_completed(occ_key):
            skipped_occurrence.append(occ_key)
            continue
        handler = registry.handler(definition.job_id)
        if handler is None:
            continue
        try:
            result = run_job_now(definition.job_id, trigger="schedule")
            mark_completed(occ_key)
            executed.append(definition.job_id)
            if result.get("state") == "SKIPPED":
                logger.info("[OPS_SCHEDULER] %s skipped: %s", definition.job_id, result.get("skip_reason"))
        except JobExecutionError as exc:
            mark_completed(occ_key)
            logger.warning("[OPS_SCHEDULER] job %s failed: %s", definition.job_id, exc)
    return {
        "executed": executed,
        "skipped_occurrences": skipped_occurrence,
        "missed_run_policy": MISSED_RUN_POLICY,
        "at": now.isoformat(),
    }


def scheduler_status() -> Dict[str, Any]:
    registry = get_job_registry()
    store = JobRunStore()
    with _lifecycle_lock:
        running = _poll_thread is not None and _poll_thread.is_alive()
    return {
        "master_enabled": is_master_enabled(),
        "legacy_schedulers_enabled": legacy_schedulers_enabled(),
        "running": running,
        "recovery_done": _recovery_done,
        "start_failed": _start_failed,
        "last_tick_at": _last_tick_at,
        "missed_run_policy": MISSED_RUN_POLICY,
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
    """Minimal schedule matcher for tests and basic cadence (America/New_York)."""
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


def reset_scheduler_state_for_tests() -> None:
    """Test hook: stop thread and allow recovery to run again."""
    global _recovery_done, _start_failed
    stop_scheduler_service()
    _recovery_done = False
    _start_failed = False
