# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — invalid profile / profile_overrides return HTTP 422 (not 500)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.server import app


def _base_request(**overrides):
    req = {
        "profile": "balanced",
        "portfolio": {"total_value": 100000.0, "available_cash": 50000.0},
        "candidates": [],
    }
    req.update(overrides)
    return req


def test_unknown_profile_returns_422() -> None:
    client = TestClient(app)
    r = client.post("/api/ui/decision-engine/evaluate", json=_base_request(profile="does_not_exist"))
    assert r.status_code == 422


def test_invalid_profile_override_value_returns_422() -> None:
    client = TestClient(app)
    # csp_delta_range outside [0,1] is invalid -> ProfileValidationError -> 422.
    r = client.post(
        "/api/ui/decision-engine/evaluate",
        json=_base_request(profile="custom", profile_overrides={"csp_delta_range": [0.1, 5.0]}),
    )
    assert r.status_code == 422


def test_unknown_override_field_returns_422() -> None:
    client = TestClient(app)
    r = client.post(
        "/api/ui/decision-engine/evaluate",
        json=_base_request(profile="custom", profile_overrides={"not_a_real_field": 1}),
    )
    assert r.status_code == 422


def test_valid_request_still_succeeds() -> None:
    client = TestClient(app)
    r = client.post("/api/ui/decision-engine/evaluate", json=_base_request())
    assert r.status_code == 200
    data = r.json()
    assert data["manual_only"] is True
    assert data["profile"]["name"] == "balanced"
