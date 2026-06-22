# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Cross-process lock, atomic writes, and a transaction journal (R34.0).

The weekly universe refresh mutates two files (the canonical overlay and the
append-only history). To make that multi-file mutation safe under concurrency
and crash-interruption, this module provides:

* :func:`cross_process_lock` — an OS-level exclusive lock (``O_CREAT|O_EXCL``
  lock file) that serializes the *entire* refresh transaction across threads
  AND processes. Lock metadata records ownership (lock_id, pid, hostname,
  process start time) so stale locks are reclaimed only when the owner is
  proven dead — never merely because the lock is older than a threshold.
* :func:`atomic_write_text` / :func:`atomic_write_json` — temp-file write with
  ``flush`` + ``fsync`` + ``os.replace`` so a reader never sees a torn file.
* A small transaction journal (:func:`write_journal`, :func:`read_journal`,
  :func:`clear_journal`) recording in-flight refresh state so an interrupted
  transaction can be deterministically recovered. Journal corruption is never
  treated as "no journal".

No scheduling and no network. Pure local filesystem coordination.
"""

from __future__ import annotations

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


class RefreshLockOwnershipError(RuntimeError):
    """Raised when lock release is attempted by a non-owner."""


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


def _process_creation_epoch(pid: int) -> Optional[float]:
    """Return process creation time (epoch seconds) for PID-reuse detection."""
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return None
            try:
                created = FILETIME()
                if not kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(created),
                    ctypes.byref(FILETIME()),
                    ctypes.byref(FILETIME()),
                    ctypes.byref(FILETIME()),
                ):
                    return None
                ft = (created.dwHighDateTime << 32) + created.dwLowDateTime
                return (ft / 10_000_000.0) - 11644473600.0
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return None
    try:
        parts = stat_path.read_text(encoding="utf-8").split()
        if len(parts) < 22:
            return None
        start_ticks = int(parts[21])
        clk_tck = os.sysconf("SC_CLK_TCK")
        uptime_sec = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        boot_epoch = time.time() - uptime_sec
        return boot_epoch + (start_ticks / clk_tck)
    except Exception:
        return None


def _process_alive(pid: int, *, process_start_epoch: Optional[float]) -> bool:
    """Return True when ``pid`` refers to the same process instance we locked."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
    if process_start_epoch is not None:
        current_start = _process_creation_epoch(pid)
        if current_start is None:
            # Cannot prove PID reuse — treat as alive (fail-safe).
            return True
        if abs(current_start - process_start_epoch) > 0.5:
            return False
    return True


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


def _read_lock_metadata(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Legacy lock files stored only a pid line.
        if raw.isdigit():
            return {
                "lock_id": "legacy",
                "pid": int(raw),
                "hostname": _hostname(),
                "created_at": path.stat().st_mtime,
                "process_start_epoch": None,
            }
        return None
    return obj if isinstance(obj, dict) else None


def _write_lock_metadata(fd: int, meta: Dict[str, Any]) -> None:
    payload = (json.dumps(meta, sort_keys=True) + "\n").encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, payload)
    os.fsync(fd)


def _lock_owner_alive(meta: Dict[str, Any]) -> bool:
    host = meta.get("hostname")
    if host and host != _hostname():
        # Another host holds the lock — fail-safe: treat as live.
        return True
    pid = meta.get("pid")
    if not isinstance(pid, int):
        return True
    start = meta.get("process_start_epoch")
    start_f = float(start) if start is not None else None
    return _process_alive(pid, process_start_epoch=start_f)


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

    Yields the lock metadata dict for the acquired lock. Lock metadata includes
    ``lock_id``, ``pid``, ``hostname``, ``created_at``, and
    ``process_start_epoch``. A lock is reclaimed only when ownership can be
    proven dead — never merely because it is older than a threshold.
    """
    path = _lock_path(name)
    deadline = time.monotonic() + timeout
    fd: Optional[int] = None
    meta: Dict[str, Any] = {}
    pid = os.getpid()
    meta = {
        "lock_id": str(uuid.uuid4()),
        "pid": pid,
        "hostname": _hostname(),
        "created_at": time.time(),
        "process_start_epoch": _process_creation_epoch(pid),
    }
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            existing = _read_lock_metadata(path)
            if existing is None:
                # Unknown ownership — wait; do not steal.
                logger.debug("[REFRESH_LOCK] lock %s present with unknown metadata; waiting", path)
            elif not _lock_owner_alive(existing):
                logger.warning(
                    "[REFRESH_LOCK] reclaiming lock %s from dead owner pid=%s",
                    path,
                    existing.get("pid"),
                )
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise RefreshLockTimeout(
                    f"could not acquire refresh lock {name!r} within {timeout}s "
                    f"(owner pid={existing.get('pid') if existing else 'unknown'})"
                )
            time.sleep(_POLL_SECONDS)
    try:
        _write_lock_metadata(fd, meta)
        yield meta
    finally:
        try:
            if fd is not None:
                os.close(fd)
        except OSError:
            pass
        try:
            if path.exists():
                current = _read_lock_metadata(path)
                if current is None:
                    raise RefreshLockOwnershipError(
                        f"lock {path} unreadable during release; not removing"
                    )
                if current.get("lock_id") != meta.get("lock_id"):
                    raise RefreshLockOwnershipError(
                        f"lock {path} owned by another holder; not removing"
                    )
                path.unlink()
        except RefreshLockOwnershipError:
            raise
        except OSError as e:
            logger.error("[REFRESH_LOCK] failed to release lock %s: %s", path, e)


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
