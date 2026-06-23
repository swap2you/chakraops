"""R33.0 — decision-engine API contract."""
from datetime import datetime, timezone

import pytest

try:
    from fastapi.testclient import TestClient
    from app.api.server import app
    _HAS_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore
    app = None  # type: ignore
    _HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")

# Use a near-now timestamp so the freshness gate (24h budget) treats it as FRESH
# regardless of when the suite runs; the server uses real time as "now".
FRESH = datetime.now(timezone.utc).isoformat()


def test_get_profiles_contract():
    client = TestClient(app)
    resp = client.get("/api/ui/decision-engine/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["profiles"].keys()) == {"conservative", "balanced", "aggressive", "custom"}
    assert body["manual_only"] is True


def test_post_evaluate_contract():
    client = TestClient(app)
    payload = {
        "profile": "balanced",
        "portfolio": {"total_value": 100000.0, "available_cash": 60000.0},
        "candidates": [
            {
                "symbol": "AAA", "strategy": "CSP", "market_regime": "BULL",
                "price": 100.0, "iv_rank": 40.0, "price_as_of": FRESH, "chain_as_of": FRESH,
                "earnings_days": 30, "sector": "TECH",
                "contract": {"delta": 0.225, "dte": 33, "premium": 2.5, "strike": 100.0,
                             "open_interest": 1000, "volume": 200, "bid_ask_spread_pct": 0.0},
            }
        ],
    }
    resp = client.post("/api/ui/decision-engine/evaluate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["manual_only"] is True
    assert body["counts"]["actionable"] == 1
    rec = body["actionable"][0]
    assert rec["decision_status"] == "ACTIONABLE"
    assert rec["manual_only"] is True
    assert rec["rank"] == 1
    assert body["stay_in_cash"]["decision_status"] == "STAY_IN_CASH"


def test_post_evaluate_blocks_stale_data():
    client = TestClient(app)
    stale = "2026-06-15T16:00:00+00:00"
    payload = {
        "profile": "balanced",
        "portfolio": {"total_value": 100000.0, "available_cash": 60000.0},
        "candidates": [
            {
                "symbol": "AAA", "strategy": "CSP", "market_regime": "BULL",
                "price": 100.0, "price_as_of": FRESH, "chain_as_of": stale, "earnings_days": 30,
                "contract": {"delta": 0.225, "dte": 33, "premium": 2.5, "strike": 100.0,
                             "open_interest": 1000, "volume": 200, "bid_ask_spread_pct": 0.0},
            }
        ],
    }
    resp = client.post("/api/ui/decision-engine/evaluate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["blocked"] == 1
    assert "STALE_OPTIONS_CHAIN" in body["blocked"][0]["reason_codes"]
