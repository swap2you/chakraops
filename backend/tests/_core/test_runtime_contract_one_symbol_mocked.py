# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Runtime contract tests for single-symbol validation endpoints (mocked; no live ORATS).

Asserts:
- GET /api/ops/snapshot and GET /api/view/symbol-diagnostics return 200 with expected shape.
- Required fields are never the string "UNKNOWN"; missing required must be null + missing_reasons.
"""

from __future__ import annotations

import pytest

# FastAPI optional
try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

# Required keys for ops/snapshot (when symbol= provided)
OPS_SNAPSHOT_KEYS = {"symbol", "snapshot_time", "snapshot", "field_sources", "missing_reasons"}

# Required keys for symbol-diagnostics
SYMBOL_DIAG_KEYS = {"symbol", "fetched_at", "stock", "gates", "blockers"}

# Stock fields that must NOT be the string "UNKNOWN" when present (use null + missing_reasons if missing)
STOCK_REQUIRED_FIELD_NAMES = ("price", "bid", "ask", "volume", "quote_date", "iv_rank")


def _stock_from_ops_snapshot(data: dict) -> dict | None:
    snap = data.get("snapshot")
    return snap if isinstance(snap, dict) else None


def _stock_from_diagnostics(data: dict) -> dict | None:
    stock = data.get("stock")
    return stock if isinstance(stock, dict) else None


def _has_unknown_placeholder_for_required(stock: dict, missing_reasons: dict) -> bool:
    """True if any required field is the string 'UNKNOWN' (invalid; must be null + missing_reasons)."""
    for name in STOCK_REQUIRED_FIELD_NAMES:
        val = stock.get(name)
        if val == "UNKNOWN":
            return True
    return False


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")
def test_ops_snapshot_returns_200_and_required_keys():
    """GET /api/ops/snapshot?symbol=AMD returns 200 and contains symbol, snapshot_time, snapshot, field_sources, missing_reasons."""
    from app.api.server import app
    client = TestClient(app)
    # Mock get_snapshot so we don't hit ORATS
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="AMD",
            price=130.0,
            bid=129.9,
            ask=130.1,
            volume=6_000_000,
            quote_date="2026-02-09",
            iv_rank=45.0,
            quote_as_of="2026-02-09T15:00:00Z",
            field_sources={"price": "strikes/options", "iv_rank": "ivrank"},
            missing_reasons={},
        )
        r = client.get("/api/ops/snapshot", params={"symbol": "AMD"})
    assert r.status_code == 200
    data = r.json()
    for key in OPS_SNAPSHOT_KEYS:
        assert key in data, f"missing key: {key}"
    assert data["symbol"] == "AMD"
    assert "snapshot_time" in data
    stock = _stock_from_ops_snapshot(data)
    assert stock is not None
    assert not _has_unknown_placeholder_for_required(stock, data.get("missing_reasons") or {}), \
        "required fields must not be string 'UNKNOWN'; use null + missing_reasons"


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")
def test_ops_snapshot_no_unknown_placeholders_for_required():
    """Snapshot and diagnostics must not use 'UNKNOWN' for required fields; use null + missing_reasons."""
    from app.api.server import app
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    client = TestClient(app)
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="AMD",
            price=None,
            bid=None,
            ask=None,
            volume=None,
            quote_date=None,
            iv_rank=None,
            field_sources={},
            missing_reasons={"price": "missing", "bid": "missing", "ask": "missing", "volume": "missing", "quote_date": "missing", "iv_rank": "missing"},
        )
        r = client.get("/api/ops/snapshot", params={"symbol": "AMD"})
    assert r.status_code == 200
    data = r.json()
    stock = _stock_from_ops_snapshot(data)
    assert stock is not None
    for name in STOCK_REQUIRED_FIELD_NAMES:
        assert stock.get(name) != "UNKNOWN", f"field {name} must not be 'UNKNOWN'; use null + missing_reasons"
    assert not _has_unknown_placeholder_for_required(stock, data.get("missing_reasons") or {})


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")
def test_symbol_diagnostics_returns_200_and_required_keys():
    """GET /api/view/symbol-diagnostics?symbol=AMD returns 200 and contains symbol, fetched_at, stock, gates, blockers."""
    from app.api.server import app
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    client = TestClient(app)
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="AMD",
            price=130.0,
            bid=129.9,
            ask=130.1,
            volume=6_000_000,
            quote_date="2026-02-09",
            iv_rank=45.0,
            quote_as_of="2026-02-09T15:00:00Z",
            field_sources={"price": "strikes/options"},
            missing_reasons={},
        )
        r = client.get("/api/view/symbol-diagnostics", params={"symbol": "AMD"})
    assert r.status_code == 200
    data = r.json()
    for key in SYMBOL_DIAG_KEYS:
        assert key in data, f"missing key: {key}"
    stock = _stock_from_diagnostics(data)
    assert stock is not None
    assert not _has_unknown_placeholder_for_required(stock, stock.get("missing_reasons") or {}), \
        "required fields must not be string 'UNKNOWN'; use null + missing_reasons"


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")
def test_symbol_diagnostics_no_unknown_placeholders_for_required():
    """Symbol-diagnostics stock must not have 'UNKNOWN' for required fields."""
    from app.api.server import app
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    client = TestClient(app)
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="TKR",
            price=100.0,
            bid=99.9,
            ask=100.1,
            volume=1_000_000,
            quote_date="2026-02-09",
            iv_rank=50.0,
            field_sources={},
            missing_reasons={},
        )
        r = client.get("/api/view/symbol-diagnostics", params={"symbol": "TKR"})
    assert r.status_code == 200
    data = r.json()
    stock = data.get("stock")
    assert isinstance(stock, dict)
    for name in STOCK_REQUIRED_FIELD_NAMES:
        assert stock.get(name) != "UNKNOWN", f"stock.{name} must not be 'UNKNOWN'"
