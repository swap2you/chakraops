# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Atomic scheduled-occurrence claim state machine (append-only, cross-process)."""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

MISSED_RUN_POLICY = "no_backfill_manual_run_required"

CLAIM_TTL_SECONDS = 3600


class OccurrenceStoreError(RuntimeError):
    """Raised when occurrence persistence or ownership checks fail."""


class OccurrenceOwnershipError(OccurrenceStoreError):
    """Raised when completion is attempted without a matching claim."""


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


def _claimant() -> str:
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"{host}:{os.getpid()}"


def _read_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OccurrenceStoreError(f"malformed occurrence record: {exc}") from exc
            if isinstance(obj, dict):
                events.append(obj)
    return events


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _reconstruct_key_state(events: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Return status COMPLETED | CLAIMED | OPEN and active claim metadata."""
    status = "OPEN"
    active_claim: Optional[Dict[str, Any]] = None
    for ev in events:
        if ev.get("key") != key:
            continue
        event = ev.get("event")
        if event == "COMPLETED":
            status = "COMPLETED"
            active_claim = None
        elif event == "RELEASED":
            if status != "COMPLETED":
                status = "OPEN"
                active_claim = None
        elif event == "CLAIMED":
            status = "CLAIMED"
            active_claim = ev
    return {"status": status, "active_claim": active_claim}


def _claim_expired(claim: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    claimed_at = _parse_ts(claim.get("claimed_at"))
    if claimed_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - claimed_at).total_seconds() >= CLAIM_TTL_SECONDS


def _append_event(record: Dict[str, Any], *, path: Path) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def claim_occurrence(
    key: str,
    *,
    job_id: str,
    run_id: str,
    scheduled_at: str,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Atomically claim an occurrence or return ALREADY_* status."""
    from app.core.universe.refresh_lock import cross_process_lock

    store = path or _store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    with cross_process_lock("scheduler_occurrences", timeout=10.0):
        events = _read_events(store)
        state = _reconstruct_key_state(events, key)
        if state["status"] == "COMPLETED":
            return {"status": "ALREADY_COMPLETED", "key": key}
        active = state.get("active_claim")
        if state["status"] == "CLAIMED" and active is not None:
            if not _claim_expired(active):
                return {
                    "status": "ALREADY_CLAIMED",
                    "key": key,
                    "claim_id": active.get("claim_id"),
                    "claimant": active.get("claimant"),
                }
            _append_event(
                {
                    "event": "RELEASED",
                    "key": key,
                    "claim_id": active.get("claim_id"),
                    "released_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "claim_expired",
                },
                path=store,
            )
        claim_id = uuid.uuid4().hex
        claim_record = {
            "event": "CLAIMED",
            "key": key,
            "job_id": job_id,
            "run_id": run_id,
            "claim_id": claim_id,
            "claimant": _claimant(),
            "scheduled_at": scheduled_at,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        }
        _append_event(claim_record, path=store)
        return {
            "status": "CLAIMED",
            "key": key,
            "claim_id": claim_id,
            "run_id": run_id,
            "claimant": claim_record["claimant"],
        }


def complete_occurrence(
    key: str,
    claim_id: str,
    *,
    path: Optional[Path] = None,
    outcome: str = "completed",
) -> None:
    """Mark occurrence completed; verifies claim ownership."""
    from app.core.universe.refresh_lock import cross_process_lock

    store = path or _store_path()
    with cross_process_lock("scheduler_occurrences", timeout=10.0):
        events = _read_events(store)
        state = _reconstruct_key_state(events, key)
        if state["status"] == "COMPLETED":
            return
        active = state.get("active_claim")
        if active is None or active.get("claim_id") != claim_id:
            raise OccurrenceOwnershipError(
                f"claim ownership mismatch for {key}: expected {claim_id!r}"
            )
        _append_event(
            {
                "event": "COMPLETED",
                "key": key,
                "claim_id": claim_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "outcome": outcome,
            },
            path=store,
        )


def release_occurrence(
    key: str,
    claim_id: str,
    *,
    reason: str = "interrupted",
    path: Optional[Path] = None,
) -> None:
    """Release an interrupted claim without completing the occurrence slot."""
    from app.core.universe.refresh_lock import cross_process_lock

    store = path or _store_path()
    with cross_process_lock("scheduler_occurrences", timeout=10.0):
        events = _read_events(store)
        state = _reconstruct_key_state(events, key)
        if state["status"] == "COMPLETED":
            return
        active = state.get("active_claim")
        if active is None or active.get("claim_id") != claim_id:
            raise OccurrenceOwnershipError(
                f"cannot release {key}: claim {claim_id!r} not active"
            )
        _append_event(
            {
                "event": "RELEASED",
                "key": key,
                "claim_id": claim_id,
                "released_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            },
            path=store,
        )


def is_completed(key: str, *, path: Optional[Path] = None) -> bool:
    state = _reconstruct_key_state(_read_events(path or _store_path()), key)
    return state["status"] == "COMPLETED"


def get_occurrence_state(key: str, *, path: Optional[Path] = None) -> Dict[str, Any]:
    return _reconstruct_key_state(_read_events(path or _store_path()), key)
