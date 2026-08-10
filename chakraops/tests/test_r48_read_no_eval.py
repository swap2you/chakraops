# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R48: page reads must not start full-universe evaluation."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_decision_latest_and_action_needed_do_not_call_evaluate_universe() -> None:
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        with patch("app.core.eval.evaluation_service_v2.evaluate_universe") as eval_mock:
            with patch("app.core.eval.eval_coordinator.run_universe_evaluation_exclusive") as coord_mock:
                client = TestClient(app)
                r1 = client.get("/api/ui/decision/latest")
                r2 = client.get("/api/ui/action-needed")
                r3 = client.get("/api/ui/system-health")
                assert r1.status_code in (200, 404, 503)
                assert r2.status_code in (200, 404, 503)
                assert r3.status_code == 200
                assert eval_mock.call_count == 0
                assert coord_mock.call_count == 0


def test_operations_status_reports_schedulers_off() -> None:
    from app.api.server import app

    client = TestClient(app)
    r = client.get("/api/operations/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("manual_only") is True
    assert body.get("trade_execution") is False
    sched = body.get("scheduler") or {}
    assert sched.get("master_enabled") is False
    assert sched.get("legacy_schedulers_enabled") is False
