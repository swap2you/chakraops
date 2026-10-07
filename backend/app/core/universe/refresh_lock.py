# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Cross-process lock, atomic writes, and a transaction journal (R34.0).

The weekly universe refresh mutates two files (the canonical overlay and the
append-only history). To make that multi-file mutation safe under concurrency
and crash-interruption, this module provides:

* :func:`cross_process_lock` — an OS-native exclusive file lock
  (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) held on an open
  file descriptor for the entire critical section. Lock acquisition uses timeout
  and retry; release drops the OS lock on the current handle. The lock file may
  remain on disk after release. No contender may unlink another process's lock;
  stale locks are never reclaimed based on age or inferred process death.
* :func:`atomic_write_text` / :func:`atomic_write_json` — temp-file write with
  ``flush`` + ``fsync`` + ``os.replace`` so a reader never sees a torn file.
* A small transaction journal (:func:`write_journal`, :func:`read_journal`,
  :func:`clear_journal`) recording in-flight refresh state so an interrupted
  transaction can be deterministically recovered. Journal corruption is never
  treated as "no journal".

No scheduling and no network. Pure local filesystem coordination.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import socket
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

# How long to wait for the lock before giving up (seconds).
DEFAULT_LOCK_TIMEOUT = 30.0
_POLL_SECONDS = 0.05

# Required journal fields for a recoverable transaction.
_JOURNAL_REQUIRED = ("week_id", "phase", "prev_overlay")


class RefreshLockTimeout(RuntimeError):
    """Raised when the cross-process lock cannot be acquired in time."""


class RefreshJournalError(RuntimeError):
    """Raised when a transaction journal is unreadable, malformed, or incomplete."""


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


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _acquire_os_lock(fd: int) -> None:
    """Acquire an exclusive OS lock on ``fd`` (non-blocking)."""
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(exc.errno, exc.strerror) from exc
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise BlockingIOError(exc.errno, exc.strerror) from exc
            raise


def _release_os_lock(fd: int) -> None:
    """Release the OS lock held on ``fd`` by this process."""
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _write_lock_metadata(fd: int, meta: Dict[str, Any]) -> None:
    """Best-effort diagnostic metadata written while the OS lock is held."""
    payload = (json.dumps(meta, sort_keys=True) + "\n").encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, payload)
    os.fsync(fd)


def _validate_journal(obj: Dict[str, Any], path: Path) -> None:
    missing = [k for k in _JOURNAL_REQUIRED if k not in obj]
    if missing:
        raise RefreshJournalError(
            f"journal at {path} missing required fields: {', '.join(missing)}"
        )
    if not isinstance(obj.get("week_id"), str) or not str(obj["week_id"]).strip():
        raise RefreshJournalError(f"journal at {path} has invalid week_id")
    if not isinstance(obj.get("phase"), str) or not str(obj["phase"]).strip():
        raise RefreshJournalError(f"journal at {path} has invalid phase")
    prev = obj.get("prev_overlay")
    if not isinstance(prev, dict):
        raise RefreshJournalError(f"journal at {path} has invalid prev_overlay")
    if "added" not in prev or "removed" not in prev:
        raise RefreshJournalError(
            f"journal at {path} prev_overlay missing added/removed lists"
        )


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
) -> Iterator[Dict[str, Any]]:
    """Acquire an exclusive cross-process lock named ``name``.

    Uses an OS-native file lock on a persistent lock file. Yields diagnostic
    metadata (``lock_id``, ``pid``, ``hostname``, ``created_at``). The lock file
    is not removed on release.
    """
    path = _lock_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    acquired = False
    meta: Dict[str, Any] = {
        "lock_id": str(uuid.uuid4()),
        "pid": os.getpid(),
        "hostname": _hostname(),
        "created_at": time.time(),
    }
    try:
        while not acquired:
            try:
                _acquire_os_lock(fd)
                acquired = True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RefreshLockTimeout(
                        f"could not acquire refresh lock {name!r} within {timeout}s"
                    )
                time.sleep(_POLL_SECONDS)
        try:
            _write_lock_metadata(fd, meta)
        except OSError as exc:
            logger.debug(
                "[REFRESH_LOCK] optional metadata write failed for %s: %s", path, exc
            )
        yield meta
    finally:
        if acquired:
            try:
                _release_os_lock(fd)
            except OSError as exc:
                logger.error(
                    "[REFRESH_LOCK] failed to release OS lock on %s: %s", path, exc
                )
        try:
            os.close(fd)
        except OSError:
            pass


def write_journal(name: str, data: Dict[str, Any]) -> None:
    """Persist an in-flight transaction journal atomically."""
    _validate_journal(data, _journal_path(name))
    atomic_write_json(_journal_path(name), data)


def read_journal(name: str) -> Optional[Dict[str, Any]]:
    """Return the journal for ``name`` if present and valid.

    Returns ``None`` only when no journal file exists. Any unreadable,
    malformed, or incomplete journal raises :class:`RefreshJournalError`.
    """
    path = _journal_path(name)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except OSError as e:
        raise RefreshJournalError(f"unreadable journal at {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise RefreshJournalError(f"malformed journal JSON at {path}: {e}") from e
    if not isinstance(obj, dict):
        raise RefreshJournalError(f"journal at {path} is not a JSON object")
    _validate_journal(obj, path)
    return obj


def clear_journal(name: str) -> None:
    """Remove the journal for ``name`` after a committed/aborted transaction."""
    path = _journal_path(name)
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as e:
        raise RefreshJournalError(f"failed to clear journal at {path}: {e}") from e
    if path.exists():
        raise RefreshJournalError(f"journal still present after clear: {path}")


def journal_path(name: str = "weekly_refresh") -> Path:
    """Public accessor for the journal path (for evidence/tests)."""
    return _journal_path(name)


def journal_exists(name: str = "weekly_refresh") -> bool:
    """Return True when a journal file exists (without validating contents)."""
    return _journal_path(name).exists()
