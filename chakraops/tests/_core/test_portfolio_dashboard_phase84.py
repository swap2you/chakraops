# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.4: Portfolio dashboard API — read-only command center."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_portfolio_dashboard_api_returns_snapshot_and_stress():
    """GET /api/portfolio/dashboard returns snapshot + stress structure."""
    try:
        from fastapi.testclient import TestClient
        from app.api.server import app
    except ImportError:
        pytest.skip("fastapi not installed")

    # Mock open_positions and equity
    positions = [
        {
            "position_id": "test-1",
            "symbol": "SPY",
            "mode": "CSP",
            "strike": 500.0,
            "contracts": 1,
            "entry_spot": 498.0,
            "status": "OPEN",
        }
    ]

    with (
        patch("app.core.portfolio.portfolio_snapshot.load_open_positions", return_value=positions),
        patch("app.core.portfolio.portfolio_snapshot.get_portfolio_equity_usd", return_value=150_000.0),
    ):
        client = TestClient(app)
        response = client.get("/api/portfolio/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert "snapshot" in data
    assert "stress" in data
    snap = data["snapshot"]
    stress = data["stress"]
    assert "total_open_positions" in snap or "total_capital_committed" in snap
    assert "scenarios" in stress
    assert "worst_case" in stress
    assert "warnings" in stress
    assert isinstance(stress["scenarios"], list)
    assert isinstance(stress["worst_case"], dict)
