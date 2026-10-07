# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified notification service for operational jobs (R35.0)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_job_failure(job_id: str, safe_message: str, severity: str = "CRITICAL") -> None:
    """Emit deduplicated in-app notification tied to a stable persisted incident."""
    from app.core.notifications.notification_safe_labels import to_safe_operator_label
    from app.core.operations.incident_store import (
        open_incident_if_absent,
        try_record_failure_notification,
    )

    opened = open_incident_if_absent(job_id, severity)
    incident_id = opened["incident_id"]
    if not try_record_failure_notification(incident_id, job_id=job_id):
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
    """Emit recovery notification only when a persisted open incident exists."""
    from app.core.operations.incident_store import (
        get_open_incident,
        try_record_recovery_notification,
    )

    open_rec = get_open_incident(job_id)
    if open_rec is None:
        return
    incident_id = str(open_rec["incident_id"])
    if not try_record_recovery_notification(job_id, incident_id):
        return
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
