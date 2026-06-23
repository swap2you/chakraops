# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Execute registered jobs with lock, timeout, retry, and safe errors."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.operations.job_registry import JobDefinition
from app.core.operations.job_run_store import JobRunStore, JobRunStoreError
from app.core.security.redact import redact_secrets, safe_provider_error

logger = logging.getLogger(__name__)

NON_RETRYABLE = frozenset({"skipped_intentional", "lock_busy"})


class JobExecutionError(RuntimeError):
    """Raised when a job fails after retries."""


def _safe_summary(exc: BaseException) -> str:
    return safe_provider_error(provider="ChakraOps", detail=exc)


def _classify_result(result: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Return terminal state and optional skip reason from handler output."""
    meta = result.get("metadata") or {}
    if meta.get("skipped") is True or result.get("skipped") is True:
        reason = meta.get("skipped_reason") or meta.get("reason") or "intentional_skip"
        return "SKIPPED", str(reason)
    if meta.get("blocked") is True:
        return "SKIPPED", "blocked_by_gate"
    return "SUCCEEDED", None


def execute_job(
    definition: JobDefinition,
    handler: Callable[[], Dict[str, Any]],
    *,
    trigger: str = "manual",
    store: Optional[JobRunStore] = None,
    skip_if_locked: bool = False,
    use_subprocess_timeout: bool = True,
) -> Dict[str, Any]:
    """Run a job with OS-native lock, bounded subprocess timeout, retry, persisted run."""
    from app.core.universe.refresh_lock import RefreshLockTimeout, cross_process_lock

    run_store = store or JobRunStore()
    run = run_store.start_run(job_id=definition.job_id, trigger=trigger)
    run_id = run["run_id"]
    attempt = 0
    last_error: Optional[str] = None
    last_classification: Optional[str] = None

    while attempt <= definition.max_retries:
        try:
            with cross_process_lock(definition.lock_name, timeout=5.0):
                start = time.monotonic()
                if use_subprocess_timeout and definition.timeout_seconds > 0:
                    from app.core.operations.job_subprocess_runner import run_handler_in_subprocess

                    result = run_handler_in_subprocess(
                        definition.job_id, definition.timeout_seconds
                    )
                else:
                    result = handler()
                elapsed_ms = int((time.monotonic() - start) * 1000)
                terminal, skip_reason = _classify_result(result)
                run_store.finish_run(
                    run_id,
                    state=terminal,
                    output_refs=list(result.get("output_refs") or []),
                    retry_count=attempt,
                    error_summary=skip_reason,
                    metadata={"duration_ms": elapsed_ms, **(result.get("metadata") or {})},
                )
                return {
                    "run_id": run_id,
                    "state": terminal,
                    "result": result,
                    "skip_reason": skip_reason,
                }
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
            last_classification = "lock_busy"
        except subprocess.TimeoutExpired:
            last_error = "job timed out"
            last_classification = "timed_out"
            if attempt >= definition.max_retries:
                break
        except JobRunStoreError as exc:
            last_error = _safe_summary(exc)
            last_classification = "store_error"
            break
        except Exception as exc:
            last_error = _safe_summary(exc)
            last_classification = "failed"
            logger.warning(
                "[JOB] %s attempt %d failed: %s",
                definition.job_id,
                attempt + 1,
                last_error,
            )
        attempt += 1
        if last_classification in NON_RETRYABLE:
            break
        if attempt <= definition.max_retries:
            delay = min(
                definition.retry_max_seconds,
                definition.retry_base_seconds * (2 ** (attempt - 1)),
            )
            time.sleep(delay)

    safe_err = redact_secrets(last_error or "unknown failure")
    terminal = "TIMED_OUT" if last_classification == "timed_out" else "FAILED"
    try:
        run_store.finish_run(
            run_id,
            state=terminal,
            error_summary=safe_err,
            retry_count=max(0, attempt - 1),
        )
    except JobRunStoreError:
        pass
    if terminal == "FAILED":
        from app.core.operations.notification_service import notify_job_failure

        notify_job_failure(definition.job_id, safe_err, definition.notification_policy)
    raise JobExecutionError(safe_err)
