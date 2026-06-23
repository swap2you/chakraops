# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified notification service for operational jobs (R35.0)."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEDUPE: Dict[str, float] = {}
_DEDUPE_TTL_SEC = 3600
_CLEARED: Set[str] = set()


def _dedupe_key(source: str, severity: str, message: str) -> str:
    raw = f"{source}|{severity}|{message}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _should_emit(key: str) -> bool:
    now = time.time()
    with _LOCK:
        if key in _CLEARED:
            return False
        last = _DEDUPE.get(key)
        if last is not None and (now - last) < _DEDUPE_TTL_SEC:
            return False
        _DEDUPE[key] = now
        return True


def notify_job_failure(job_id: str, safe_message: str, severity: str = "CRITICAL") -> None:
    """Emit deduplicated in-app notification for job failure."""
    from app.core.notifications.notification_safe_labels import to_safe_operator_label

    label = to_safe_operator_label(job_id) or job_id
    msg = f"Job {label} failed: {safe_message}"
    key = _dedupe_key(job_id, severity, msg)
    if not _should_emit(key):
        return
    try:
        from app.api.notifications_store import append_notification

        append_notification(
            severity,
            f"JOB_{job_id.upper()}_FAILED",
            msg,
            subtype=f"job_failure:{job_id}",
        )
    except Exception as exc:
        logger.warning("[OPS_NOTIFY] failed to persist notification: %s", exc)


def notify_job_recovery(job_id: str, safe_message: str) -> None:
    key = _dedupe_key(job_id, "INFO", f"recovered:{safe_message}")
    with _LOCK:
        _CLEARED.add(_dedupe_key(job_id, "CRITICAL", ""))
    if not _should_emit(key):
        return
    try:
        from app.api.notifications_store import append_notification

        append_notification(
            "INFO",
            f"JOB_{job_id.upper()}_RECOVERED",
            f"Job {job_id} recovered: {safe_message}",
            subtype=f"job_recovery:{job_id}",
        )
    except Exception as exc:
        logger.warning("[OPS_NOTIFY] recovery notification failed: %s", exc)


def notify_orats_unavailable(safe_message: str) -> None:
    notify_job_failure("provider_health", safe_message, severity="CRITICAL")
