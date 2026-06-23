# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 operations API tests."""

from __future__ import annotations

import pytest


def test_operations_status_endpoint():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    resp = client.get("/api/operations/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["manual_only"] is True
    assert body["trade_execution"] is False
    assert "scheduler" in body


def test_operations_jobs_list():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    resp = client.get("/api/operations/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) >= 8
