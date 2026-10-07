# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.9: Portfolio guardrails + sizing caps — deterministic, safe labels only, no FAIL_/WARN_."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock


def test_guardrails_config_returns_dict_with_defaults() -> None:
    """get_guardrails_config() returns dict with expected keys and default values."""
    from app.core.settings import get_guardrails_config

    cfg = get_guardrails_config()
    assert isinstance(cfg, dict)
    assert cfg.get("MAX_OPEN_OPTIONS_POSITIONS") == 6
    assert cfg.get("MAX_OPEN_SHARES_POSITIONS") == 10
    assert cfg.get("MAX_SYMBOLS_EXPOSURE") == 12
    assert cfg.get("MAX_NOTIONAL_PER_SYMBOL_PCT") == 15.0
    assert cfg.get("MIN_CASH_RESERVE_PCT") == 25.0
    assert cfg.get("OPTIONS_MAX_RISK_PER_TRADE_PCT") == 2.0
    assert cfg.get("SECTOR_EXPOSURE_ADVISORY_PCT") == 35.0


def test_compute_portfolio_metrics_deterministic() -> None:
    """Same snapshot -> same metrics (determinism)."""
    from app.core.portfolio.guardrails_r259 import compute_portfolio_metrics

    snapshot = {
        "cash": 50_000,
        "total_capital": 100_000,
        "holdings": [{"symbol": "AAPL", "shares": 100, "avg_cost": 150.0}],
        "share_positions": [],
        "option_positions": [{"symbol": "NVDA", "strategy": "CSP", "contracts": 1, "strike": 100.0}],
        "symbol_prices": {},
    }
    m1 = compute_portfolio_metrics(snapshot)
    m2 = compute_portfolio_metrics(snapshot)
    assert m1["open_options_count"] == m2["open_options_count"]
    assert m1["open_shares_count"] == m2["open_shares_count"]
    assert m1["symbols_exposure_count"] == m2["symbols_exposure_count"]
    assert m1["cash_reserve_pct"] == m2["cash_reserve_pct"]


def test_evaluate_guardrails_cash_reserve_blocks_entry() -> None:
    """When cash reserve below min, ENTRY is blocked (hard_blocks)."""
    from app.core.portfolio.guardrails_r259 import (
        evaluate_guardrails_for_entry,
        REASON_CASH_RESERVE,
        STATUS_BLOCKED,
    )

    metrics = {
        "open_options_count": 0,
        "open_shares_count": 0,
        "symbols_exposure_count": 0,
        "total_equity": 100_000,
        "cash_reserve_pct": 10.0,
        "max_symbol_notional_pct": 5.0,
        "symbol_notionals": {},
        "sector_exposure_pct": None,
    }
    config = {"MIN_CASH_RESERVE_PCT": 25.0, "MAX_OPEN_OPTIONS_POSITIONS": 6, "MAX_OPEN_SHARES_POSITIONS": 10, "MAX_SYMBOLS_EXPOSURE": 12, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0, "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0, "SECTOR_EXPOSURE_ADVISORY_PCT": 35.0}
    out = evaluate_guardrails_for_entry(metrics, {"symbol": "AAPL", "strategy": "OPTIONS"}, config=config)
    assert out["status"] == STATUS_BLOCKED
    assert REASON_CASH_RESERVE in (out.get("hard_blocks") or [])


def test_evaluate_guardrails_max_open_options_blocks_options_entry() -> None:
    """When max open options reached, options ENTRY is blocked."""
    from app.core.portfolio.guardrails_r259 import (
        evaluate_guardrails_for_entry,
        REASON_MAX_OPEN_OPTIONS,
        STATUS_BLOCKED,
    )

    config = {"MIN_CASH_RESERVE_PCT": 25.0, "MAX_OPEN_OPTIONS_POSITIONS": 6, "MAX_OPEN_SHARES_POSITIONS": 10, "MAX_SYMBOLS_EXPOSURE": 12, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0, "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0, "SECTOR_EXPOSURE_ADVISORY_PCT": 35.0}
    metrics = {
        "open_options_count": 6,
        "open_shares_count": 0,
        "symbols_exposure_count": 5,
        "total_equity": 100_000,
        "cash_reserve_pct": 50.0,
        "max_symbol_notional_pct": 8.0,
        "symbol_notionals": {},
        "sector_exposure_pct": None,
    }
    out = evaluate_guardrails_for_entry(metrics, {"symbol": "NEW", "strategy": "OPTIONS"}, config=config)
    assert out["status"] == STATUS_BLOCKED
    assert REASON_MAX_OPEN_OPTIONS in (out.get("hard_blocks") or [])


def test_evaluate_guardrails_sector_advisory_does_not_block() -> None:
    """Sector exposure over advisory -> advisories only, status not Blocked."""
    from app.core.portfolio.guardrails_r259 import (
        evaluate_guardrails_for_entry,
        REASON_SECTOR_ADVISORY,
        STATUS_ADVISORY,
    )

    config = {"MIN_CASH_RESERVE_PCT": 25.0, "MAX_OPEN_OPTIONS_POSITIONS": 6, "MAX_OPEN_SHARES_POSITIONS": 10, "MAX_SYMBOLS_EXPOSURE": 12, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0, "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0, "SECTOR_EXPOSURE_ADVISORY_PCT": 35.0}
    metrics = {
        "open_options_count": 2,
        "open_shares_count": 1,
        "symbols_exposure_count": 3,
        "total_equity": 100_000,
        "cash_reserve_pct": 40.0,
        "max_symbol_notional_pct": 10.0,
        "symbol_notionals": {},
        "sector_exposure_pct": 45.0,
    }
    out = evaluate_guardrails_for_entry(metrics, {"symbol": "AAPL", "strategy": "OPTIONS"}, config=config)
    assert out["status"] == STATUS_ADVISORY
    assert REASON_SECTOR_ADVISORY in (out.get("advisories") or [])
    assert not (out.get("hard_blocks") or [])


def test_evaluate_guardrails_deterministic_reason_ordering() -> None:
    """hard_blocks and advisories are sorted (deterministic ordering)."""
    from app.core.portfolio.guardrails_r259 import evaluate_guardrails_for_entry

    config = {"MIN_CASH_RESERVE_PCT": 25.0, "MAX_OPEN_OPTIONS_POSITIONS": 6, "MAX_OPEN_SHARES_POSITIONS": 10, "MAX_SYMBOLS_EXPOSURE": 12, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0, "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0, "SECTOR_EXPOSURE_ADVISORY_PCT": 35.0}
    metrics = {
        "open_options_count": 6,
        "open_shares_count": 10,
        "symbols_exposure_count": 13,
        "total_equity": 100_000,
        "cash_reserve_pct": 5.0,
        "max_symbol_notional_pct": 20.0,
        "symbol_notionals": {"AAPL": 20_000},
        "sector_exposure_pct": 50.0,
    }
    out = evaluate_guardrails_for_entry(metrics, {"symbol": "AAPL", "strategy": "OPTIONS"}, config=config)
    blocks = out.get("hard_blocks") or []
    assert blocks == sorted(blocks)
    advisories = out.get("advisories") or []
    assert advisories == sorted(advisories)


def test_guardrails_status_values_safe_only() -> None:
    """Status and reason codes never contain FAIL or WARN (word-boundary)."""
    from app.core.portfolio.guardrails_r259 import (
        STATUS_OK,
        STATUS_ADVISORY,
        STATUS_BLOCKED,
        evaluate_guardrails_for_entry,
    )

    assert "FAIL" not in STATUS_OK and "WARN" not in STATUS_OK
    assert "FAIL" not in STATUS_ADVISORY and "WARN" not in STATUS_ADVISORY
    assert "FAIL" not in STATUS_BLOCKED and "WARN" not in STATUS_BLOCKED

    config = {"MIN_CASH_RESERVE_PCT": 25.0, "MAX_OPEN_OPTIONS_POSITIONS": 6, "MAX_OPEN_SHARES_POSITIONS": 10, "MAX_SYMBOLS_EXPOSURE": 12, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0, "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0, "SECTOR_EXPOSURE_ADVISORY_PCT": 35.0}
    metrics = {"open_options_count": 0, "open_shares_count": 0, "symbols_exposure_count": 0, "total_equity": 100_000, "cash_reserve_pct": 5.0, "max_symbol_notional_pct": 0, "symbol_notionals": {}, "sector_exposure_pct": None}
    out = evaluate_guardrails_for_entry(metrics, {"symbol": "X", "strategy": "OPTIONS"}, config=config)
    raw = json.dumps(out)
    assert "FAIL_" not in raw and "WARN_" not in raw
    assert "FAIL" not in raw.split() and "WARN" not in raw.split()


def test_system_health_includes_guardrails_no_forbidden_substrings() -> None:
    """GET /api/ui/system-health includes guardrails block; no FAIL_/WARN_ in payload."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    assert "guardrails" in data
    g = data["guardrails"]
    assert "status" in g
    assert g["status"] in ("OK", "Advisory", "Blocked")
    assert "metrics" in g
    assert "limits" in g
    raw = json.dumps(data)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_action_needed_payload_no_fail_warn_substrings() -> None:
    """Action-needed API response contains no FAIL_/WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200
    data = r.json()
    raw = json.dumps(data)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
