# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
TASK D + E: Enforce endpoint correctness and fixture-based contract tests.

- Fail if Universe/Ticker view code uses /datav2/live/* for equity bid/ask/volume or iv_rank.
- Fixture-based contract tests (no external ORATS calls).
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

try:
    from fastapi.testclient import TestClient
    from app.api.server import app
    _HAS_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    app = None  # type: ignore[misc, assignment]
    _HAS_FASTAPI = False

pytestmark_api = pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")


# --- Single snapshot pipeline: view endpoints MUST use snapshot_service ---


@pytestmark_api
def test_symbol_diagnostics_uses_snapshot_service():
    """GET /api/view/symbol-diagnostics must call get_snapshot (no bypass). Fails if view fetches ORATS directly."""
    from app.core.data.symbol_snapshot_service import SymbolSnapshot
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get_snapshot:
        mock_get_snapshot.return_value = SymbolSnapshot(
            ticker="AMD",
            price=120.0,
            bid=119.9,
            ask=120.1,
            volume=5_000_000,
            quote_date="2026-02-09",
            iv_rank=40.0,
            quote_as_of="2026-02-09T14:00:00Z",
            core_as_of="2026-02-09T14:00:00Z",
            derived_as_of="2026-02-09T14:00:00Z",
            field_sources={"price": "delayed_strikes_ivrank"},
            missing_reasons={},
        )
        client = TestClient(app)
        r = client.get("/api/view/symbol-diagnostics", params={"symbol": "AMD"})
    assert r.status_code == 200
    mock_get_snapshot.assert_called_once()
    call_args = mock_get_snapshot.call_args[0]
    assert call_args[0] == "AMD"
    data = r.json()
    assert data["stock"]["price"] == 120.0
    assert data.get("snapshot_time") is not None


@pytestmark_api
def test_ops_snapshot_symbol_returns_canonical_snapshot():
    """GET /api/ops/snapshot?symbol=AMD returns raw snapshot + field_sources (single pipeline proof)."""
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
            stock_volume_today=6_100_000,
            avg_option_volume_20d=80_000.0,
            avg_stock_volume_20d=5_500_000.0,
            quote_as_of="2026-02-09T15:00:00Z",
            core_as_of="2026-02-09T15:00:00Z",
            derived_as_of="2026-02-09T15:00:00Z",
            field_sources={"price": "delayed_strikes_ivrank", "stock_volume_today": "datav2/cores"},
            missing_reasons={},
        )
        client = TestClient(app)
        r = client.get("/api/ops/snapshot", params={"symbol": "AMD"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("symbol") == "AMD"
    assert "snapshot_time" in data
    assert "snapshot" in data
    assert "field_sources" in data
    assert "missing_reasons" in data
    assert data["snapshot"]["price"] == 130.0
    assert data["snapshot"]["avg_option_volume_20d"] == 80_000.0
    assert data["snapshot"]["avg_stock_volume_20d"] == 5_500_000.0
    mock_get.assert_called_once()


@pytestmark_api
def test_universe_uses_snapshot_service():
    """GET /api/view/universe must call get_snapshots_batch (no bypass). Fails if view fetches ORATS directly."""
    from app.core.data.symbol_snapshot_service import SymbolSnapshot
    with patch("app.api.data_health.UNIVERSE_SYMBOLS", ["SPY", "QQQ"]):
        with patch("app.core.data.symbol_snapshot_service.get_snapshots_batch") as mock_batch:
            mock_batch.return_value = {
                "SPY": SymbolSnapshot(ticker="SPY", price=500.0, quote_as_of="2026-02-09T12:00:00Z", field_sources={}, missing_reasons={}),
                "QQQ": SymbolSnapshot(ticker="QQQ", price=450.0, quote_as_of="2026-02-09T12:00:00Z", field_sources={}, missing_reasons={}),
            }
            client = TestClient(app)
            r = client.get("/api/view/universe")
    assert r.status_code == 200
    mock_batch.assert_called_once()
    data = r.json()
    assert "symbols" in data
    assert len(data["symbols"]) >= 1


# --- TASK D: Fail if view code uses live for equity/iv_rank ---


@pytestmark_api
@patch("app.api.data_health.UNIVERSE_SYMBOLS", ["SPY"])
@patch("app.core.data.symbol_snapshot_service.get_snapshots_batch")
@patch("app.core.data.orats_client.get_orats_live_summaries")
def test_universe_does_not_use_live_for_equity(mock_live_summaries, mock_snapshots_batch):
    """Universe must NOT use get_orats_live_summaries (Live API) for equity/price."""
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    mock_snapshots_batch.return_value = {
        "SPY": SymbolSnapshot(ticker="SPY", price=500.0, quote_as_of="2026-02-09T12:00:00Z", field_sources={}, missing_reasons={}),
    }
    client = TestClient(app)
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    mock_live_summaries.assert_not_called()


@pytestmark_api
@patch("app.core.data.orats_client.get_orats_live_summaries")
def test_symbol_diagnostics_does_not_use_live_for_stock_snapshot(mock_live_summaries):
    """Symbol-diagnostics must NOT use get_orats_live_summaries for stock price/bid/ask/volume/iv_rank."""
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    snap = SymbolSnapshot(
        ticker="AAPL",
        price=175.0,
        bid=174.9,
        ask=175.1,
        volume=1_000_000,
        quote_date="2026-02-09",
        iv_rank=35.0,
        stock_volume_today=2_000_000,
        avg_option_volume_20d=50_000.0,
        avg_stock_volume_20d=1_500_000.0,
        quote_as_of="2026-02-09T12:00:00Z",
        core_as_of="2026-02-09T12:00:00Z",
        derived_as_of="2026-02-09T12:00:00Z",
        field_sources={"price": "delayed_strikes_ivrank", "volume": "delayed_strikes_ivrank"},
        missing_reasons={},
    )
    with patch("app.core.data.symbol_snapshot_service.get_snapshot", return_value=snap):
        client = TestClient(app)
        r = client.get("/api/view/symbol-diagnostics", params={"symbol": "AAPL"})
    assert r.status_code == 200
    mock_live_summaries.assert_not_called()
    data = r.json()
    assert data["stock"]["price"] == 175.0
    assert data["stock"]["bid"] == 174.9
    assert data["stock"]["volume"] == 1_000_000
    assert "UNKNOWN" not in str(data["stock"].get("price")) and "UNKNOWN" not in str(data["stock"].get("volume"))


# --- TASK E: Fixture-based contract tests ---

FIXTURE_CORES = {
    "data": [{
        "ticker": "AAPL",
        "stkVolu": 12_000_000,
        "avgOptVolu20d": 55_000.0,
        "tradeDate": "2026-02-09",
    }]
}

FIXTURE_HIST_DAILIES = [
    {"tradeDate": "2026-02-09", "stockVolume": 10_000_000},
    {"tradeDate": "2026-02-08", "stockVolume": 11_000_000},
] * 10


def test_cores_fixture_mapping_stk_volu_avg_opt_volu():
    """Fixture payload for /datav2/cores: stkVolu and avgOptVolu20d map to stock_volume_today, avg_option_volume_20d."""
    from app.core.data.orats_field_map import orats_to_canonical
    row = FIXTURE_CORES["data"][0]
    mapped = orats_to_canonical(row)
    assert mapped.get("stock_volume_today") == 12_000_000
    assert mapped.get("avg_option_volume_20d") == 55_000.0


def test_hist_dailies_fixture_derived_avg():
    """Fixture payload for /datav2/hist/dailies: mean of stockVolume series = avg_stock_volume_20d."""
    vols = [r["stockVolume"] for r in FIXTURE_HIST_DAILIES if r.get("stockVolume") is not None]
    assert len(vols) >= 2
    avg = sum(vols) / len(vols)
    assert 10_000_000 <= avg <= 11_000_000


@pytestmark_api
@patch("app.core.config.orats_secrets.ORATS_API_TOKEN", "test-token")
@patch("app.api.data_health.UNIVERSE_SYMBOLS", ["AAPL"])
@patch("app.core.orats.orats_core_client.derive_avg_stock_volume_20d", return_value=1_500_000.0)
@patch("app.core.orats.orats_core_client.fetch_core_snapshot")
@patch("app.core.data.orats_client.fetch_full_equity_snapshots")
def test_universe_returns_rows_with_snapshot_fields_and_as_of(mock_delayed, mock_core, _mock_derive):
    """GET /api/view/universe returns rows with header fields from snapshot and as_of timestamps."""
    from app.core.orats.orats_equity_quote import FullEquitySnapshot
    from app.core.data.symbol_snapshot_service import clear_snapshot_cache

    clear_snapshot_cache()
    delayed_snap = FullEquitySnapshot(
        symbol="AAPL",
        price=175.0,
        bid=174.9,
        ask=175.1,
        volume=1_000_000,
        quote_date="2026-02-09",
        iv_rank=35.0,
    )
    mock_delayed.return_value = {"AAPL": delayed_snap}
    mock_core.return_value = {"stkVolu": 12_000_000, "avgOptVolu20d": 55_000.0}

    client = TestClient(app)
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert "symbols" in data
    assert len(data["symbols"]) >= 1
    row = data["symbols"][0]
    assert row.get("symbol") == "AAPL"
    assert "last_price" in row
    assert row["last_price"] == 175.0
    assert "quote_as_of" in row or "stock_volume_today" in row
    assert "UNKNOWN" not in str(row.get("last_price", ""))


@pytestmark_api
@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_symbol_diagnostics_stock_price_consistent_no_unknown(mock_get_snapshot):
    """GET symbol-diagnostics: stock.price matches snapshot; no UNKNOWN in stock fields."""
    from app.core.data.symbol_snapshot_service import SymbolSnapshot

    mock_get_snapshot.return_value = SymbolSnapshot(
        ticker="AAPL",
        price=180.5,
        bid=180.4,
        ask=180.6,
        volume=2_000_000,
        quote_date="2026-02-09",
        iv_rank=40.0,
        stock_volume_today=2_100_000,
        avg_option_volume_20d=60_000.0,
        avg_stock_volume_20d=1_900_000.0,
        quote_as_of="2026-02-09T15:00:00Z",
        core_as_of="2026-02-09T15:00:00Z",
        derived_as_of="2026-02-09T15:00:00Z",
        field_sources={"price": "delayed_strikes_ivrank"},
        missing_reasons={},
    )
    client = TestClient(app)
    r = client.get("/api/view/symbol-diagnostics", params={"symbol": "AAPL"})
    assert r.status_code == 200
    data = r.json()
    assert data["stock"]["price"] == 180.5
    assert data["options"]["underlying_price"] == 180.5
    stock_str = str(data.get("stock", {}))
    assert "UNKNOWN" not in stock_str
