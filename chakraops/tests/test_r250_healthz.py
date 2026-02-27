# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.0: GET /api/healthz — lightweight health check (no ORATS, no heavy state)."""

from __future__ import annotations

import re

import pytest


def test_api_healthz_returns_200_and_ok_ts():
    """GET /api/healthz returns 200 with status ok and iso ts."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    client = TestClient(app)
    r = client.get("/api/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("ok") is True
    ts = data.get("ts")
    assert ts is not None
    # ISO format with timezone (e.g. 2026-02-26T19:00:00.123456+00:00)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts) is not None
