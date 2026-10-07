# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 scheduler lifecycle tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_scheduler(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_SCHEDULER_ENABLED", raising=False)
    from app.core.operations import scheduler_service as svc

    svc.reset_scheduler_state_for_tests()
    yield
    svc.stop_scheduler_service()
    svc.reset_scheduler_state_for_tests()


def test_disabled_startup_then_enable_starts_thread(monkeypatch):
    from app.core.operations import scheduler_service as svc

    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "false")
    svc.start_scheduler_service()
    assert svc.scheduler_status()["recovery_done"] is True
    assert svc.scheduler_status()["running"] is False

    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "true")
    svc.start_scheduler_service()
    assert svc.scheduler_status()["running"] is True


def test_stop_then_restart(monkeypatch):
    from app.core.operations import scheduler_service as svc

    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "true")
    svc.start_scheduler_service()
    assert svc.scheduler_status()["running"] is True
    svc.stop_scheduler_service()
    assert svc.scheduler_status()["running"] is False
    svc.start_scheduler_service()
    assert svc.scheduler_status()["running"] is True


def test_repeated_start_idempotent(monkeypatch):
    from app.core.operations import scheduler_service as svc

    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "true")
    svc.start_scheduler_service()
    t1 = svc._poll_thread
    svc.start_scheduler_service()
    assert svc._poll_thread is t1


def test_failed_start_cleanup(monkeypatch):
    from app.core.operations import scheduler_service as svc

    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "true")
    with patch.object(svc.threading, "Thread", side_effect=RuntimeError("boom")):
        svc.start_scheduler_service()
    assert svc.scheduler_status()["start_failed"] is True
    assert svc.scheduler_status()["running"] is False
