# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Cross-process lock, atomic writes, and a transaction journal (R34.0).

The weekly universe refresh mutates two files (the canonical overlay and the
append-only history). To make that multi-file mutation safe under concurrency
and crash-interruption, this module provides:

* :func:`cross_process_lock` — an OS-level exclusive lock (``O_CREAT|O_EXCL``
  lock file) that serializes the *entire* refresh transaction across threads
  AND processes. Includes stale-lock recovery so a crashed holder cannot
  deadlock the system forever.
* :func:`atomic_write_text` / :func:`atomic_write_json` — temp-file write with
  ``flush`` + ``fsync`` + ``os.replace`` so a reader never sees a torn file.
* A small transaction journal (:func:`write_journal`, :func:`read_journal`,
  :func:`clear_journal`) recording in-flight refresh state so an interrupted
  transaction can be deterministically recovered.

No scheduling and no network. Pure local filesystem coordination.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import logging

logger = logging.getLogger(__name__)

# How long to wait for the lock before giving up (seconds).
DEFAULT_LOCK_TIMEOUT = 30.0
# A lock file older than this is treated as abandoned by a crashed holder.
STALE_LOCK_SECONDS = 120.0
_POLL_SECONDS = 0.05


class RefreshLockTimeout(RuntimeError):
    """Raised when the cross-process lock cannot be acquired in time."""


def _coord_dir() -> Path:
    """Directory holding lock + journal files (under the output dir)."""
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    d = base / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lock_path(name: str) -> Path:
    return _coord_dir() / f"{name}.lock"


def _journal_path(name: str) -> Path:
    return _coord_dir() / f"{name}.journal.json"


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp + fsync + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        # Clean up the temp file if os.replace did not consume it.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialize ``payload`` to JSON and write it atomically."""
    atomic_write_text(Path(path), json.dumps(payload, indent=2, sort_keys=True))


@contextmanager
def cross_process_lock(
    name: str = "weekly_refresh",
    timeout: float = DEFAULT_LOCK_TIMEOUT,
    stale_after: float = STALE_LOCK_SECONDS,
) -> Iterator[None]:
    """Acquire an exclusive cross-process lock named ``name``.

    Serializes the whole refresh transaction. Uses an exclusive-create lock
    file so concurrent threads and processes contend for the same token. If a
    prior holder crashed and left a stale lock file (older than ``stale_after``
    seconds), it is reclaimed so the system cannot deadlock permanently.
    """
    path = _lock_path(name)
    deadline = time.monotonic() + timeout
    fd: Optional[int] = None
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            # Contended. Reclaim if the existing lock is stale.
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > stale_after:
                logger.warning(
                    "[REFRESH_LOCK] reclaiming stale lock %s (age=%.1fs)", path, age
                )
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise RefreshLockTimeout(
                    f"could not acquire refresh lock {name!r} within {timeout}s"
                )
            time.sleep(_POLL_SECONDS)
    try:
        try:
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        except OSError:
            pass
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass


def write_journal(name: str, data: Dict[str, Any]) -> None:
    """Persist an in-flight transaction journal atomically."""
    atomic_write_json(_journal_path(name), data)


def read_journal(name: str) -> Optional[Dict[str, Any]]:
    """Return the journal for ``name`` if a transaction was interrupted."""
    path = _journal_path(name)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_journal(name: str) -> None:
    """Remove the journal for ``name`` (transaction committed/aborted cleanly)."""
    try:
        _journal_path(name).unlink()
    except OSError:
        pass


def journal_path(name: str = "weekly_refresh") -> Path:
    """Public accessor for the journal path (for evidence/tests)."""
    return _journal_path(name)
