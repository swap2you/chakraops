# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run job handlers in an isolated child process with hard timeout."""

from __future__ import annotations

import logging
import multiprocessing
import subprocess
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def _child_entry(job_id: str, out_queue: "multiprocessing.Queue") -> None:
    import os
    import time

    test_behavior = os.getenv("CHAKRAOPS_TEST_JOB_BEHAVIOR", "")
    if test_behavior == "hang":
        time.sleep(60)
        out_queue.put(("ok", {"output_refs": []}))
        return
    try:
        from app.core.operations.job_registry import get_job_registry

        handler = get_job_registry().handler(job_id)
        if handler is None:
            out_queue.put(("error", f"unknown job: {job_id}"))
            return
        result = handler()
        out_queue.put(("ok", result))
    except Exception as exc:
        out_queue.put(("error", repr(exc)))


def run_handler_in_subprocess(job_id: str, timeout_seconds: float) -> Dict[str, Any]:
    """Execute ``job_id`` handler in a spawn child; terminate child on timeout."""
    if timeout_seconds <= 0:
        from app.core.operations.job_registry import get_job_registry

        handler = get_job_registry().handler(job_id)
        if handler is None:
            raise KeyError(f"unknown job: {job_id}")
        return handler()

    ctx = multiprocessing.get_context("spawn")
    out_queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(target=_child_entry, args=(job_id, out_queue), daemon=True)
    proc.start()
    proc.join(timeout=timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(5.0)
        if proc.is_alive():
            proc.kill()
            proc.join(2.0)
        raise subprocess.TimeoutExpired(cmd=job_id, timeout=timeout_seconds)

    if out_queue.empty():
        raise RuntimeError(f"job child produced no result for {job_id}")

    status, payload = out_queue.get_nowait()
    if status == "ok":
        if not isinstance(payload, dict):
            raise RuntimeError(f"job {job_id} returned non-dict result")
        return payload
    raise RuntimeError(str(payload))
