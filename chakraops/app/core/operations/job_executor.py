# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Execute registered jobs with lock, timeout, retry, and safe errors."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Optional

from app.core.operations.job_registry import JobDefinition
from app.core.operations.job_run_store import JobRunStore
from app.core.security.redact import redact_secrets, safe_provider_error

logger = logging.getLogger(__name__)


class JobExecutionError(RuntimeError):
    """Raised when a job fails after retries."""


def _safe_summary(exc: BaseException) -> str:
    return safe_provider_error(provider="ChakraOps", detail=exc)


def execute_job(
    definition: JobDefinition,
    handler: Callable[[], Dict[str, Any]],
    *,
    trigger: str = "manual",
    store: Optional[JobRunStore] = None,
    skip_if_locked: bool = False,
) -> Dict[str, Any]:
    """Run a job with OS-native lock, timeout, bounded retry, persisted run record."""
    from app.core.universe.refresh_lock import RefreshLockTimeout, cross_process_lock

    run_store = store or JobRunStore()
    run = run_store.start_run(job_id=definition.job_id, trigger=trigger)
    run_id = run["run_id"]
    attempt = 0
    last_error: Optional[str] = None

    while attempt <= definition.max_retries:
        try:
            with cross_process_lock(definition.lock_name, timeout=5.0):
                start = time.monotonic()
                result = _run_with_timeout(handler, definition.timeout_seconds)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                run_store.finish_run(
                    run_id,
                    state="SUCCEEDED",
                    output_refs=list(result.get("output_refs") or []),
                    retry_count=attempt,
                    metadata={"duration_ms": elapsed_ms, **(result.get("metadata") or {})},
                )
                return {"run_id": run_id, "state": "SUCCEEDED", "result": result}
        except RefreshLockTimeout:
            if skip_if_locked:
                run_store.finish_run(
                    run_id,
                    state="SKIPPED",
                    error_summary="lock held by another process",
                    lock_status="busy",
                )
                return {"run_id": run_id, "state": "SKIPPED", "reason": "lock_busy"}
            last_error = "could not acquire job lock"
        except subprocess.TimeoutExpired:
            last_error = "job timed out"
            if attempt >= definition.max_retries:
                break
        except Exception as exc:
            last_error = _safe_summary(exc)
            logger.warning(
                "[JOB] %s attempt %d failed: %s",
                definition.job_id,
                attempt + 1,
                last_error,
            )
        attempt += 1
        if attempt <= definition.max_retries:
            delay = min(
                definition.retry_max_seconds,
                definition.retry_base_seconds * (2 ** (attempt - 1)),
            )
            time.sleep(delay)

    safe_err = redact_secrets(last_error or "unknown failure")
    run_store.finish_run(
        run_id,
        state="TIMED_OUT" if last_error == "job timed out" else "FAILED",
        error_summary=safe_err,
        retry_count=max(0, attempt - 1),
    )
    from app.core.operations.notification_service import notify_job_failure

    notify_job_failure(definition.job_id, safe_err, definition.notification_policy)
    raise JobExecutionError(safe_err)


def _run_with_timeout(handler: Callable[[], Dict[str, Any]], timeout_seconds: float) -> Dict[str, Any]:
    if timeout_seconds <= 0:
        return handler()
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(handler)
        try:
            return fut.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise subprocess.TimeoutExpired(cmd=handler.__name__, timeout=timeout_seconds) from exc
