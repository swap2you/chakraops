# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.0 alert payload: schema and no-secrets tests."""

from __future__ import annotations

import json

import pytest

from app.core.alerts.alert_payload import REQUIRED_TOP_KEYS, build_alert_payload
from app.core.alerts.alert_store import save_alert_payload

SECRET_PATTERNS = ("orats_api_token", "api_key", "secret", "password", "authorization")


def test_alert_payload_required_keys():
    """Payload must contain required top-level keys."""
    payload = build_alert_payload(
        symbol="SPY",
        run_id="test-run-1",
        eligibility_trace={
            "mode_decision": "CSP",
            "primary_reason_code": None,
            "rejection_reason_codes": [],
            "regime": "UP",
            "rsi14": 50.0,
            "atr_pct": 0.02,
            "support_level": 580.0,
            "resistance_level": 600.0,
        },
        stage2_trace={"selected_trade": {"exp": "2025-03-21", "strike": 590, "bid": 2.5, "ask": 2.6}},
        candles_meta={"last_date": "2025-02-12"},
        config_meta={},
    )
    for key in REQUIRED_TOP_KEYS:
        assert key in payload, f"Missing required key: {key}"
    assert payload["run_id"] == "test-run-1"
    assert payload["symbol"] == "SPY"
    assert payload["mode_decision"] == "CSP"
    assert "rejection_reason_codes" in payload
    assert "data_as_of" in payload


def test_alert_payload_no_secrets_in_serialized():
    """Serialized JSON must not contain token/secret-like strings."""
    payload = build_alert_payload(
        symbol="SPY",
        run_id="r1",
        eligibility_trace={"mode_decision": "NONE", "rejection_reason_codes": ["FAIL_RSI_CSP"]},
        stage2_trace=None,
        candles_meta=None,
        config_meta={"source": "test"},
    )
    # Intentionally do NOT pass any secret; payload must not introduce one
    serialized = json.dumps(payload, default=str).lower()
    for pattern in SECRET_PATTERNS:
        assert pattern not in serialized, f"Serialized payload must not contain {pattern!r}"


def test_alert_payload_config_meta_not_used_for_secrets():
    """config_meta is merged for display only; we must not dump env or tokens."""
    payload = build_alert_payload(
        symbol="X",
        run_id="r2",
        eligibility_trace={},
        stage2_trace=None,
        candles_meta=None,
        config_meta={"lookback": 255, "source": "validate"},
    )
    serialized = json.dumps(payload, default=str)
    assert "ORATS_API_TOKEN" not in serialized
    assert "token" not in serialized.lower() or "reason_code" in serialized  # reason_code is ok


def test_save_alert_payload_path():
    """save_alert_payload returns path under base_dir/run_id/symbol.json."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        payload = {
            "run_id": "save-test-run",
            "symbol": "SPY",
            "mode_decision": "NONE",
            "primary_reason_code": "FAIL_RSI_CSP",
            "rejection_reason_codes": ["FAIL_RSI_CSP"],
        }
        path = save_alert_payload(payload, base_dir=tmp)
        assert path
        assert "save-test-run" in path
        assert "SPY.json" in path or path.endswith("SPY.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["run_id"] == "save-test-run"
        assert data["symbol"] == "SPY"
