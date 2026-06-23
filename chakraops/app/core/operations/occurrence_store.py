# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Persist completed scheduler occurrences (job_id + scheduled local slot)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Set
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# Missed-run policy: occurrences are not backfilled after the slot passes.
# If the process was down during a slot, the operator must run the job manually.
MISSED_RUN_POLICY = "no_backfill_manual_run_required"


def _store_path() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "scheduler_occurrences.jsonl"


def scheduled_slot(job_id: str, now: datetime) -> str:
    """Deterministic local ET slot string for an occurrence key."""
    local = now.astimezone(_ET) if now.tzinfo else now.replace(tzinfo=_ET)
    if job_id == "provider_health":
        bucket = local.replace(minute=(local.minute // 30) * 30, second=0, microsecond=0)
        return bucket.strftime("%Y-%m-%dT%H:%M")
    if job_id == "weekly_universe_refresh":
        return local.strftime("%Y-%m-%d") + "T06:00"
    if job_id == "eod_data_refresh":
        return local.strftime("%Y-%m-%d") + "T16:10"
    if job_id in ("decision_generation", "nightly_reports"):
        return local.strftime("%Y-%m-%d") + "T19:00"
    if job_id == "backup":
        return local.strftime("%Y-%m-%d") + "T02:00"
    if job_id == "retention_cleanup":
        return local.strftime("%Y-%m-%d") + "T03:00"
    return local.strftime("%Y-%m-%dT%H:%M")


def occurrence_key(job_id: str, now: datetime) -> str:
    return f"{job_id}|{scheduled_slot(job_id, now)}"


def _read_keys(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    keys: Set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed occurrence record: {exc}") from exc
            key = obj.get("key")
            if isinstance(key, str):
                keys.add(key)
    return keys


def is_completed(key: str, *, path: Optional[Path] = None) -> bool:
    return key in _read_keys(path or _store_path())


def mark_completed(key: str, *, path: Optional[Path] = None) -> None:
    from app.core.universe.refresh_lock import cross_process_lock

    path = path or _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "key": key,
        "completed_at": datetime.now(_ET).isoformat(),
        "timezone": "America/New_York",
    }
    with cross_process_lock("scheduler_occurrences", timeout=10.0):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
