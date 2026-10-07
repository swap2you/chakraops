# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Persist job-failure incidents with atomic open/dedupe (cross-process)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class IncidentStoreError(RuntimeError):
    """Raised when incident persistence is malformed or unsafe."""


def _path() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "job_incidents.jsonl"


def _read_all(path: Path) -> List[Dict[str, Any]]:
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
                raise IncidentStoreError(f"malformed incident record: {exc}") from exc
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _append_unlocked(record: Dict[str, Any], *, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _lock():
    from app.core.universe.refresh_lock import cross_process_lock

    return cross_process_lock("job_incidents", timeout=10.0)


def _reconstruct_open(
    events: List[Dict[str, Any]], job_id: str, failure_class: str = "default"
) -> Optional[Dict[str, Any]]:
    open_rec: Optional[Dict[str, Any]] = None
    for rec in events:
        if rec.get("job_id") != job_id:
            continue
        if rec.get("failure_class", "default") != failure_class:
            continue
        event = rec.get("event")
        if event == "open":
            open_rec = rec
        elif event == "close" and open_rec and rec.get("incident_id") == open_rec.get(
            "incident_id"
        ):
            open_rec = None
    return open_rec


def get_open_incident(
    job_id: str,
    *,
    failure_class: str = "default",
    path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    return _reconstruct_open(_read_all(path or _path()), job_id, failure_class)


def open_incident_if_absent(
    job_id: str,
    severity: str,
    *,
    failure_class: str = "default",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Atomically open an incident or return the existing open incident."""
    p = path or _path()
    with _lock():
        events = _read_all(p)
        existing = _reconstruct_open(events, job_id, failure_class)
        if existing:
            return {
                "incident_id": str(existing["incident_id"]),
                "created": False,
                "job_id": job_id,
                "failure_class": failure_class,
            }
        incident_id = f"{job_id}:{uuid.uuid4().hex[:12]}"
        _append_unlocked(
            {
                "event": "open",
                "incident_id": incident_id,
                "job_id": job_id,
                "severity": severity,
                "failure_class": failure_class,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            },
            path=p,
        )
        return {
            "incident_id": incident_id,
            "created": True,
            "job_id": job_id,
            "failure_class": failure_class,
        }


def open_incident(job_id: str, severity: str, *, path: Optional[Path] = None) -> str:
    """Backward-compatible wrapper."""
    return open_incident_if_absent(job_id, severity, path=path)["incident_id"]


def _has_event(events: List[Dict[str, Any]], incident_id: str, event: str) -> bool:
    return any(
        rec.get("incident_id") == incident_id and rec.get("event") == event for rec in events
    )


def try_record_failure_notification(
    incident_id: str,
    *,
    job_id: str,
    path: Optional[Path] = None,
) -> bool:
    """Return True when this process should emit the failure notification."""
    p = path or _path()
    with _lock():
        events = _read_all(p)
        if _has_event(events, incident_id, "failure_notified"):
            return False
        _append_unlocked(
            {
                "event": "failure_notified",
                "incident_id": incident_id,
                "job_id": job_id,
                "notified_at": datetime.now(timezone.utc).isoformat(),
            },
            path=p,
        )
        return True


def try_record_recovery_notification(
    job_id: str,
    incident_id: str,
    *,
    path: Optional[Path] = None,
) -> bool:
    """Atomically close incident and record recovery notification once."""
    p = path or _path()
    with _lock():
        events = _read_all(p)
        open_rec = _reconstruct_open(events, job_id)
        if open_rec is None or open_rec.get("incident_id") != incident_id:
            return False
        if _has_event(events, incident_id, "recovery_notified"):
            return False
        _append_unlocked(
            {
                "event": "recovery_notified",
                "incident_id": incident_id,
                "job_id": job_id,
                "notified_at": datetime.now(timezone.utc).isoformat(),
            },
            path=p,
        )
        _append_unlocked(
            {
                "event": "close",
                "incident_id": incident_id,
                "job_id": job_id,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
            path=p,
        )
        return True


def close_incident(job_id: str, incident_id: str, *, path: Optional[Path] = None) -> None:
    p = path or _path()
    with _lock():
        _append_unlocked(
            {
                "event": "close",
                "incident_id": incident_id,
                "job_id": job_id,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
            path=p,
        )
