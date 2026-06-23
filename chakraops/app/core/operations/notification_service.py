# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified notification service for operational jobs (R35.0)."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Dict, Set

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEDUPE: Dict[str, float] = {}
_DEDUPE_TTL_SEC = 3600
_EMITTED_RECOVERY: Set[str] = set()


def _dedupe_key(incident_id: str, kind: str) -> str:
    return hashlib.sha256(f"{incident_id}|{kind}".encode("utf-8")).hexdigest()[:16]


def _should_emit(key: str) -> bool:
    now = time.time()
    with _LOCK:
        last = _DEDUPE.get(key)
        if last is not None and (now - last) < _DEDUPE_TTL_SEC:
            return False
        _DEDUPE[key] = now
        return True


def notify_job_failure(job_id: str, safe_message: str, severity: str = "CRITICAL") -> None:
    """Emit deduplicated in-app notification tied to a stable incident."""
    from app.core.notifications.notification_safe_labels import to_safe_operator_label
    from app.core.operations.incident_store import get_open_incident, open_incident

    incident_id = open_incident(job_id, severity)
    dedupe = _dedupe_key(incident_id, "failure")
    if not _should_emit(dedupe):
        return
    label = to_safe_operator_label(job_id) or job_id
    msg = f"Job {label} failed: {safe_message}"
    try:
        from app.api.notifications_store import append_notification

        append_notification(
            severity,
            f"JOB_{job_id.upper()}_FAILED",
            msg,
            subtype=f"job_failure:{job_id}",
            details={"incident_id": incident_id, "job_id": job_id},
        )
    except Exception as exc:
        logger.warning("[OPS_NOTIFY] failed to persist notification: %s", exc)


def notify_job_recovery(job_id: str, safe_message: str) -> None:
    from app.core.operations.incident_store import close_incident, get_open_incident

    open_rec = get_open_incident(job_id)
    if open_rec is None:
        return
    incident_id = str(open_rec["incident_id"])
    dedupe = _dedupe_key(incident_id, "recovery")
    with _LOCK:
        if incident_id in _EMITTED_RECOVERY:
            return
    if not _should_emit(dedupe):
        return
    close_incident(job_id, incident_id)
    with _LOCK:
        _EMITTED_RECOVERY.add(incident_id)
    try:
        from app.api.notifications_store import append_notification

        append_notification(
            "INFO",
            f"JOB_{job_id.upper()}_RECOVERED",
            f"Job {job_id} recovered: {safe_message}",
            subtype=f"job_recovery:{job_id}",
            details={"incident_id": incident_id, "job_id": job_id},
        )
    except Exception as exc:
        logger.warning("[OPS_NOTIFY] recovery notification failed: %s", exc)


def notify_orats_unavailable(safe_message: str) -> None:
    notify_job_failure("provider_health", safe_message, severity="CRITICAL")
