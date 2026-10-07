# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 17.0: File locking for JSONL append stores — lock file under out/.locks/."""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF_MS = 10
_MAX_BACKOFF_MS = 200


def _lock_path_for_store_path(store_path: Path) -> Path:
    """Derive lock file path: <parent>/.locks/<name>.lock"""
    parent = store_path.parent
    locks_dir = parent / ".locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    name = store_path.name
    return locks_dir / f"{name}.lock"


@contextmanager
def with_file_lock(store_path: Path, timeout_ms: int = 2000) -> Generator[None, None, None]:
    """
    Acquire an exclusive lock for the given store path.
    Lock file is created under <store_parent>/.locks/<store_name>.lock.
    Uses O_CREAT|O_EXCL (create exclusive) with retry/backoff up to timeout_ms.
    """
    lock_path = _lock_path_for_store_path(Path(store_path))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.perf_counter() + (timeout_ms / 1000.0)
    backoff_ms = _INITIAL_BACKOFF_MS
    fd = None
    try:
        while time.perf_counter() < deadline:
            try:
                fd = os.open(
                    str(lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.fsync(fd)
                break
            except FileExistsError:
                time.sleep(backoff_ms / 1000.0)
                backoff_ms = min(backoff_ms * 2, _MAX_BACKOFF_MS)
                continue
        else:
            raise TimeoutError(f"Could not acquire lock for {store_path} within {timeout_ms}ms")
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                lock_path.unlink(missing_ok=True)
            except OSError as e:
                logger.debug("[LOCKS] Failed to release lock %s: %s", lock_path, e)
