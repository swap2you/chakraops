# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical decision generation job — advisory only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.core.operations.job_registry import JobDefinition, JobRegistry


def _run() -> Dict[str, Any]:
    from app.core.data_reliability.freshness import evaluate_freshness, stale_data_gate
    from app.core.decision_engine.live_service import compute_live_recommendations
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2

    store = get_evaluation_store_v2()
    artifact = store.get_latest()
    if artifact is None:
        return {
            "output_refs": ["blocked_no_artifact"],
            "metadata": {"blocked": True, "reason": "NO_DECISION_ARTIFACT"},
        }

    now = datetime.now(timezone.utc)
    as_of = getattr(artifact, "as_of", None) or getattr(artifact, "evaluated_at", None)
    parsed = None
    if as_of:
        try:
            parsed = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            parsed = None
    gate = stale_data_gate(
        [
            evaluate_freshness(
                "DECISION_ARTIFACT",
                parsed,
                max_age_seconds=48 * 3600,
                now=now,
                required=True,
            )
        ]
    )
    if gate.blocked:
        return {
            "output_refs": ["blocked_stale_data"],
            "metadata": {"blocked": True, "reason_codes": list(gate.reason_codes or [])},
        }

    canonical = compute_live_recommendations(artifact, profile_name="balanced")
    recs = canonical.get("recommendations") or []
    count = len(recs) if isinstance(recs, list) else 0
    return {
        "output_refs": [f"recommendations={count}"],
        "metadata": {"count": count, "decision_source": canonical.get("decision_source")},
    }


def register(registry: JobRegistry) -> None:
    registry.register(
        JobDefinition(
            job_id="decision_generation",
            purpose="Generate top 5-7 advisory canonical decisions",
            owner="operations",
            schedule_cron="Mon-Fri 19:00 America/New_York",
            timezone="America/New_York",
            lock_name="job_decision_generation",
            timeout_seconds=900.0,
            max_retries=1,
            retry_base_seconds=30.0,
            retry_max_seconds=120.0,
            notification_policy="WARNING",
            failure_classification="decision_blocked",
            manual_command="POST /api/operations/jobs/decision_generation/run",
            recovery_procedure="Refresh data; verify canonical artifact; retry manual run",
            input_dependencies=["decision_store_v2", "fresh ORATS data"],
            freshness_requirements=["stale_data_gate pass"],
            output_artifacts=["authoritative_recommendations"],
            enabled_env_var="CHAKRAOPS_JOB_DECISION_GENERATION_ENABLED",
        ),
        _run,
    )
