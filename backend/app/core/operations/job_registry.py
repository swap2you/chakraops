# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical job inventory for R35.0 operational readiness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    purpose: str
    owner: str
    schedule_cron: str  # human-readable; e.g. "Sun 06:00 America/New_York"
    timezone: str
    lock_name: str
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float
    retry_max_seconds: float
    notification_policy: str  # INFO|WARNING|CRITICAL on failure
    failure_classification: str
    manual_command: str
    recovery_procedure: str
    input_dependencies: List[str] = field(default_factory=list)
    freshness_requirements: List[str] = field(default_factory=list)
    output_artifacts: List[str] = field(default_factory=list)
    enabled_env_var: str = ""
    schedule_env_var: str = ""

    def is_enabled(self) -> bool:
        var = self.enabled_env_var or f"CHAKRAOPS_JOB_{self.job_id.upper()}_ENABLED"
        return os.getenv(var, "false").lower() in ("true", "1", "yes")

    def to_dict(self, *, handler: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "purpose": self.purpose,
            "owner": self.owner,
            "enabled": self.is_enabled(),
            "schedule": self.schedule_cron,
            "timezone": self.timezone,
            "input_dependencies": list(self.input_dependencies),
            "freshness_requirements": list(self.freshness_requirements),
            "lock_name": self.lock_name,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": {
                "max_retries": self.max_retries,
                "base_seconds": self.retry_base_seconds,
                "max_delay_seconds": self.retry_max_seconds,
            },
            "output_artifacts": list(self.output_artifacts),
            "notification_policy": self.notification_policy,
            "failure_classification": self.failure_classification,
            "manual_command": self.manual_command,
            "recovery_procedure": self.recovery_procedure,
            "handler_registered": handler is not None,
        }


class JobRegistry:
    """Authoritative in-memory job registry (single registration point)."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobDefinition] = {}
        self._handlers: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def register(
        self,
        definition: JobDefinition,
        handler: Callable[[], Dict[str, Any]],
    ) -> None:
        if definition.job_id in self._jobs:
            raise ValueError(f"duplicate job registration: {definition.job_id}")
        self._jobs[definition.job_id] = definition
        self._handlers[definition.job_id] = handler

    def get(self, job_id: str) -> Optional[JobDefinition]:
        return self._jobs.get(job_id)

    def handler(self, job_id: str) -> Optional[Callable[[], Dict[str, Any]]]:
        return self._handlers.get(job_id)

    def list_jobs(self) -> List[JobDefinition]:
        return list(self._jobs.values())

    def inventory(self) -> List[Dict[str, Any]]:
        return [
            d.to_dict(handler=self._handlers.get(d.job_id))
            for d in self.list_jobs()
        ]


_REGISTRY: Optional[JobRegistry] = None


def get_job_registry() -> JobRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = JobRegistry()
        _register_builtin_jobs(_REGISTRY)
    return _REGISTRY


def _register_builtin_jobs(registry: JobRegistry) -> None:
    from app.core.operations.jobs import register_all_jobs

    register_all_jobs(registry)
