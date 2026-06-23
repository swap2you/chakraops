# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Persisted job-run records for R35.0 — cross-process safe."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN_STATES = (
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "SKIPPED",
    "TIMED_OUT",
    "RECOVERED",
)

TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "SKIPPED", "TIMED_OUT", "RECOVERED"})


class JobRunStoreError(RuntimeError):
    """Raised when job-run persistence is invalid or unsafe."""


def _runs_path() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "job_runs.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_lock():
    from app.core.universe.refresh_lock import cross_process_lock

    return cross_process_lock("job_run_store", timeout=30.0)


class JobRunStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or _runs_path()

    def start_run(
        self,
        *,
        job_id: str,
        trigger: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = {
            "run_id": str(uuid.uuid4()),
            "job_id": job_id,
            "state": "STARTED",
            "trigger": trigger,
            "started_at": _now_iso(),
            "ended_at": None,
            "duration_ms": None,
            "retry_count": 0,
            "error_summary": None,
            "output_refs": [],
            "lock_status": "acquired",
            "metadata": metadata or {},
        }
        with _store_lock():
            self._append_unlocked(record)
        return record

    def finish_run(
        self,
        run_id: str,
        *,
        state: str,
        error_summary: Optional[str] = None,
        output_refs: Optional[List[str]] = None,
        retry_count: int = 0,
        lock_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if state not in RUN_STATES:
            raise JobRunStoreError(f"invalid run state: {state}")
        with _store_lock():
            runs = self._read_all_unlocked()
            updated = False
            for rec in runs:
                if rec.get("run_id") != run_id:
                    continue
                current = rec.get("state")
                if current in TERMINAL_STATES and current != state:
                    raise JobRunStoreError(
                        f"cannot regress terminal state {current!r} -> {state!r} for {run_id}"
                    )
                started = rec.get("started_at")
                ended = _now_iso()
                rec["state"] = state
                rec["ended_at"] = ended
                rec["retry_count"] = retry_count
                if error_summary is not None:
                    rec["error_summary"] = error_summary
                if output_refs is not None:
                    rec["output_refs"] = output_refs
                if lock_status is not None:
                    rec["lock_status"] = lock_status
                if metadata:
                    rec["metadata"] = {**(rec.get("metadata") or {}), **metadata}
                if started:
                    try:
                        s = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        e = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                        rec["duration_ms"] = int((e - s).total_seconds() * 1000)
                    except Exception:
                        pass
                updated = True
                break
            if not updated:
                return
            self._rewrite_unlocked(runs)

    def read_all(self, limit: int = 500) -> List[Dict[str, Any]]:
        with _store_lock():
            return self._read_all_unlocked(limit=limit)

    def recent_for_job(self, job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return [r for r in reversed(self.read_all()) if r.get("job_id") == job_id][:limit]

    def interrupted_started_runs(self) -> List[Dict[str, Any]]:
        return [r for r in self.read_all() if r.get("state") == "STARTED"]

    def mark_recovered(self, run_id: str, note: str) -> None:
        self.finish_run(run_id, state="RECOVERED", error_summary=note)

    def _read_all_unlocked(self, limit: int = 500) -> List[Dict[str, Any]]:
        path = self.path
        if not path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise JobRunStoreError(f"malformed job run line: {exc}") from exc
                if isinstance(obj, dict):
                    out.append(obj)
        return out[-limit:]

    def _append_unlocked(self, record: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _rewrite_unlocked(self, records: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
