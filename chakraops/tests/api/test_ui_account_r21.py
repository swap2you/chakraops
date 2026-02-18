# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.1: API tests for /api/ui/account/* (summary, holdings, balances)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_out(tmp_path):
    """Use tmp_path for out dir so account.db is isolated."""
    with patch("app.core.accounts.holdings_db._db_path") as m:
        m.return_value = tmp_path / "account.db"
        yield tmp_path


def test_account_summary_returns_structure(temp_out):
    """GET /api/ui/account/summary returns account_id, cash, buying_power, holdings_count."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    r = client.get("/api/ui/account/summary")
    assert r.status_code == 200
    data = r.json()
    assert "account_id" in data
    assert "cash" in data
    assert "buying_power" in data
    assert "holdings_count" in data
    assert data["holdings_count"] >= 0


def test_account_holdings_list(temp_out):
    """GET /api/ui/account/holdings returns holdings list."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    r = client.get("/api/ui/account/holdings")
    assert r.status_code == 200
    data = r.json()
    assert "holdings" in data
    assert isinstance(data["holdings"], list)


def test_account_holdings_upsert_and_delete(temp_out):
    """POST /api/ui/account/holdings adds holding; DELETE removes it."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    # Add
    r = client.post(
        "/api/ui/account/holdings",
        json={"symbol": "NVDA", "shares": 225, "avg_cost": 95.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert "holding" in body
    assert body["holding"]["symbol"] == "NVDA"
    assert body["holding"]["shares"] == 225
    assert body["holding"]["avg_cost"] == 95.0

    # List includes it
    r2 = client.get("/api/ui/account/holdings")
    assert r2.status_code == 200
    holdings = r2.json()["holdings"]
    nvda = next((h for h in holdings if h["symbol"] == "NVDA"), None)
    assert nvda is not None
    assert nvda["shares"] == 225

    # Delete
    r3 = client.delete("/api/ui/account/holdings/NVDA")
    assert r3.status_code == 200
    r4 = client.get("/api/ui/account/holdings")
    nvda_after = next((h for h in r4.json()["holdings"] if h["symbol"] == "NVDA"), None)
    assert nvda_after is None


def test_account_holdings_upsert_validation(temp_out):
    """POST without symbol or shares returns 400."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    r = client.post("/api/ui/account/holdings", json={})
    assert r.status_code == 400
    r2 = client.post("/api/ui/account/holdings", json={"symbol": "AAPL"})
    assert r2.status_code == 400


def test_account_balances_set(temp_out):
    """POST /api/ui/account/balances sets cash and buying_power."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    r = client.post(
        "/api/ui/account/balances",
        json={"cash": 50000.0, "buying_power": 48000.0},
    )
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert data["summary"]["cash"] == 50000.0
    assert data["summary"]["buying_power"] == 48000.0
