# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 optional API — SIMULATION flags; separate from journal backtest."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "r40"


def test_r40_run_api_returns_simulation_flags() -> None:
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.post(
            "/api/ui/backtest/r40/run",
            json={
                "profile": "balanced",
                "fixture_dir": str(FIXTURE),
                "train_start": "2024-01-01",
                "train_end": "2024-06-30",
                "oos_start": "2024-07-01",
                "oos_end": "2024-12-31",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["simulation"] is True
    assert body["manual_only"] is True
    assert body.get("label") == "SIMULATION"
    assert body["oos"]["metrics"]["trade_count"] == 5
    raw = json.dumps(body)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_r40_run_rejects_look_ahead() -> None:
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.post(
            "/api/ui/backtest/r40/run",
            json={
                "profile": "balanced",
                "fixture_dir": str(FIXTURE),
                "train_start": "2024-01-01",
                "train_end": "2024-08-01",
                "oos_start": "2024-07-01",
                "oos_end": "2024-12-31",
            },
        )
    assert r.status_code == 400


def test_r40_last_when_missing() -> None:
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        with patch("app.api.ui_routes._repo_root") as root:
            # Point at a temp path with no last-run file
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                root.return_value = Path(tmp) / "chakraops"
                client = TestClient(app)
                r = client.get("/api/ui/backtest/r40/last")
    assert r.status_code == 200
    assert r.json()["present"] is False
    assert r.json()["simulation"] is True
