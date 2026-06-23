# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Persist open job-failure incidents for notification correlation."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _path() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "job_incidents.jsonl"


def _read_all(path: Optional[Path] = None) -> list[Dict[str, Any]]:
    p = path or _path()
    if not p.exists():
        return []
    out: list[Dict[str, Any]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed incident record: {exc}") from exc
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _append(record: Dict[str, Any], *, path: Optional[Path] = None) -> None:
    from app.core.universe.refresh_lock import cross_process_lock

    p = path or _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with cross_process_lock("job_incidents", timeout=10.0):
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())


def get_open_incident(job_id: str, *, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for rec in reversed(_read_all(path)):
        if rec.get("job_id") == job_id and rec.get("event") == "open":
            return rec
        if rec.get("job_id") == job_id and rec.get("event") == "close":
            return None
    return None


def open_incident(job_id: str, severity: str, *, path: Optional[Path] = None) -> str:
    existing = get_open_incident(job_id, path=path)
    if existing:
        return str(existing["incident_id"])
    incident_id = f"{job_id}:{uuid.uuid4().hex[:12]}"
    _append(
        {
            "event": "open",
            "incident_id": incident_id,
            "job_id": job_id,
            "severity": severity,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        },
        path=path,
    )
    return incident_id


def close_incident(job_id: str, incident_id: str, *, path: Optional[Path] = None) -> None:
    _append(
        {
            "event": "close",
            "incident_id": incident_id,
            "job_id": job_id,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        },
        path=path,
    )
