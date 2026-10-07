# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.8: Options position enrichment for portfolio; deterministic sort; no FAIL_/WARN_ in payloads."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.positions.models import Position
from app.core.portfolio.options_enrichment_r278 import enrich_options_positions_for_portfolio


def _make_position(
    position_id: str = "pos_1",
    symbol: str = "SPY",
    strategy: str = "CSP",
    strike: float = 400.0,
    expiration: str = "2026-04-18",
    contracts: int = 1,
    open_credit: float = 2.5,
    mark_price_per_contract: float | None = 1.2,
    status: str = "OPEN",
    mark_time_utc: str | None = None,
) -> Position:
    return Position(
        position_id=position_id,
        account_id="default",
        symbol=symbol,
        strategy=strategy,
        contracts=contracts,
        strike=strike,
        expiration=expiration,
        credit_expected=open_credit,
        open_credit=open_credit,
        status=status,
        opened_at="2026-02-01T12:00:00Z",
        mark_price_per_contract=mark_price_per_contract,
        mark_time_utc=mark_time_utc,
    )


def test_enrich_options_positions_deterministic_sort() -> None:
    """Options positions are sorted by (symbol, expiration, strike) for determinism."""
    a = _make_position(position_id="a", symbol="AAPL", expiration="2026-05-20", strike=150.0)
    z = _make_position(position_id="z", symbol="ZZZ", expiration="2026-03-15", strike=100.0)
    m = _make_position(position_id="m", symbol="AAPL", expiration="2026-04-18", strike=155.0)
    positions = [a, z, m]
    out = enrich_options_positions_for_portfolio(positions, {}, None)
    assert len(out) == 3
    order = [o["symbol"] + "|" + (o.get("expiration") or "") + "|" + str(o.get("strike") or 0) for o in out]
    assert order == ["AAPL|2026-04-18|155.0", "AAPL|2026-05-20|150.0", "ZZZ|2026-03-15|100.0"]


def test_enrich_options_positions_only_open_csp_cc() -> None:
    """Only OPEN/PARTIAL_EXIT and strategy CSP/CC are included."""
    open_csp = _make_position(position_id="1", strategy="CSP", status="OPEN")
    closed_csp = _make_position(position_id="2", strategy="CSP", status="CLOSED")
    open_cc = _make_position(position_id="3", strategy="CC", status="OPEN")
    stock = _make_position(position_id="4", symbol="SPY", strategy="STOCK", status="OPEN", contracts=0)
    positions = [open_csp, closed_csp, open_cc, stock]
    out = enrich_options_positions_for_portfolio(positions, {}, None)
    assert len(out) == 2
    ids = {o["position_id"] for o in out}
    assert ids == {"1", "3"}


def test_enrich_options_positions_safe_labels_no_fail_warn() -> None:
    """Enriched payload must not contain FAIL_ or WARN_ substrings."""
    p = _make_position(mark_price_per_contract=1.0)
    out = enrich_options_positions_for_portfolio([p], {}, None)
    assert len(out) == 1
    raw = json.dumps(out[0])
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
    assert out[0].get("lifecycle_recommend") in ("Hold", "Roll", "Close")
    assert out[0].get("lifecycle_reason") is not None


def test_enrich_options_positions_has_mark_dte_pct_max_profit() -> None:
    """Enriched option has mark_value/source/age, dte, pct_max_profit when mark present."""
    p = _make_position(open_credit=2.0, mark_price_per_contract=1.0)
    out = enrich_options_positions_for_portfolio([p], {}, None)
    assert len(out) == 1
    o = out[0]
    assert o.get("mark_value") == 1.0
    assert o.get("dte") is not None
    assert o.get("pct_max_profit") is not None  # (2-1)/2*100 = 50
    assert "lifecycle_recommend" in o
    assert "lifecycle_reason" in o


def test_portfolio_response_no_fail_warn_substrings() -> None:
    """GET /portfolio and GET /portfolio/options must not contain FAIL_ or WARN_ in JSON."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/portfolio")
    assert r.status_code == 200
    raw = json.dumps(r.json())
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
    for opt in r.json().get("options_positions") or []:
        assert "FAIL_" not in json.dumps(opt)
        assert "WARN_" not in json.dumps(opt)

    with patch("app.api.ui_routes._require_ui_key"):
        r2 = client.get("/api/ui/portfolio/options")
    assert r2.status_code == 200
    raw2 = json.dumps(r2.json())
    assert "FAIL_" not in raw2
    assert "WARN_" not in raw2
