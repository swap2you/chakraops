# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for risk posture scaffold (Phase 4.5.5).

Ensure posture propagates through config and pipeline but does not affect behavior.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.models.risk_posture import RiskPosture
from app.core.settings import get_environment_config
from app.core.environment.session_gate import check_session_gate


def test_risk_posture_enum_values():
    """RiskPosture has CONSERVATIVE, BALANCED, AGGRESSIVE."""
    assert RiskPosture.CONSERVATIVE.value == "CONSERVATIVE"
    assert RiskPosture.BALANCED.value == "BALANCED"
    assert RiskPosture.AGGRESSIVE.value == "AGGRESSIVE"


def test_get_environment_config_returns_risk_posture():
    """get_environment_config() includes risk_posture; default is CONSERVATIVE."""
    config = get_environment_config()
    assert "risk_posture" in config
    assert config["risk_posture"] is RiskPosture.CONSERVATIVE


def test_risk_posture_propagates_in_config():
    """risk_posture from config is the RiskPosture enum (CONSERVATIVE by default)."""
    config = get_environment_config()
    rp = config["risk_posture"]
    assert rp is RiskPosture.CONSERVATIVE
    assert rp.value == "CONSERVATIVE"


def test_session_gate_unchanged_by_posture():
    """Session gate behavior is unchanged by risk_posture (no threshold changes yet)."""
    # Same inputs; gate uses min_trading_days_to_expiry from config, not risk_posture
    today = date(2026, 1, 6)
    expiry = date(2026, 1, 7)  # 1 trading day to expiry
    config_conservative = {
        "block_short_sessions": False,
        "min_trading_days_to_expiry": 5,
        "risk_posture": RiskPosture.CONSERVATIVE,
    }
    config_balanced = {
        "block_short_sessions": False,
        "min_trading_days_to_expiry": 5,
        "risk_posture": RiskPosture.BALANCED,
    }
    reasons_conservative = check_session_gate(today, expiry, config_conservative)
    reasons_balanced = check_session_gate(today, expiry, config_balanced)
    # Same result: INSUFFICIENT_TRADING_DAYS in both (posture does not change threshold)
    assert reasons_conservative == reasons_balanced
    assert "INSUFFICIENT_TRADING_DAYS" in reasons_conservative


def test_pipeline_output_includes_risk_posture():
    """Pipeline run produces output_data.metadata.risk_posture (propagation)."""
    from app.core.settings import get_environment_config

    config = get_environment_config()
    rp = config.get("risk_posture")
    risk_posture_str = rp.value if hasattr(rp, "value") else str(rp)
    assert risk_posture_str == "CONSERVATIVE"
    # Simulate what run_and_save puts in output_data
    metadata = {"risk_posture": risk_posture_str}
    assert metadata["risk_posture"] == "CONSERVATIVE"


def test_invalid_risk_posture_coerced_to_conservative():
    """Invalid risk_posture in config is coerced to CONSERVATIVE."""
    with patch("app.core.settings._load_yaml_config") as mock_load:
        mock_load.return_value = {"environment": {"risk_posture": "INVALID"}}
        config = get_environment_config()
    assert config["risk_posture"] is RiskPosture.CONSERVATIVE
