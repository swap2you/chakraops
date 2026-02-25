# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.3: Position lifecycle (request-time only), action-needed no FAIL_/WARN_, determinism."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.lifecycle.position_lifecycle_r243 import (
    RECOMMENDED_BY,
    compute_position_lifecycle,
    PROFIT_TARGET_PCT_DEFAULT,
    ROLL_WINDOW_DTE_DEFAULT,
)


class _MockPosition:
    def __init__(self, strategy="CSP", strike=100.0, expiration="2026-04-18", open_credit=2.50, mark_price_per_contract=None):
        self.strategy = strategy
        self.strike = strike
        self.expiration = expiration
        self.open_credit = open_credit
        self.mark_price_per_contract = mark_price_per_contract
        self.credit_expected = open_credit


def test_lifecycle_recommended_by():
    assert RECOMMENDED_BY == "r243"


def test_lifecycle_non_option_returns_hold():
    pos = _MockPosition(strategy="STOCK")
    out = compute_position_lifecycle(pos)
    assert out["recommended_action_code"] == "HOLD"
    assert out["recommended_by"] == "r243"
    assert out["dte"] is None


def test_lifecycle_profit_target_hit_close():
    pos = _MockPosition(open_credit=2.0, mark_price_per_contract=0.50)
    out = compute_position_lifecycle(pos, mark_proxy=0.50, profit_target_pct=50.0)
    # (2 - 0.5) / 2 * 100 = 75% -> CLOSE
    assert out["pct_max_profit"] == 75.0
    assert out["recommended_action_code"] == "CLOSE"


def test_lifecycle_roll_window():
    pos = _MockPosition(expiration="2026-03-01")  # near expiry
    out = compute_position_lifecycle(pos)
    assert out["roll_window"]["active"] is True
    assert out["recommended_action_code"] in ("ROLL", "CLOSE", "HOLD")


def test_lifecycle_deterministic():
    pos = _MockPosition(open_credit=2.0, mark_price_per_contract=1.0)
    a = compute_position_lifecycle(pos, spot=99.0)
    b = compute_position_lifecycle(pos, spot=99.0)
    assert a["pct_max_profit"] == b["pct_max_profit"]
    assert a["recommended_action_code"] == b["recommended_action_code"]
    assert a["recommended_by"] == b["recommended_by"]


def test_lifecycle_fields_not_in_decision_artifact():
    """R24.3: Lifecycle fields must not be persisted in decision_latest.json."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2
    import json
    artifact = DecisionArtifactV2(metadata={"run_id": "test"}, symbols=[], selected_candidates=[])
    data = artifact.to_dict_persist()
    json_str = json.dumps(data, default=str)
    assert "assignment_risk" not in json_str
    assert "roll_window" not in json_str


def test_action_needed_response_no_fail_warn():
    """R24.3: GET /api/ui/action-needed must not contain FAIL_ or WARN_ in JSON."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    def _strings_in_obj(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from _strings_in_obj(v)
        elif isinstance(obj, list):
            for x in obj:
                yield from _strings_in_obj(x)

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200, r.text
    data = r.json()
    for s in _strings_in_obj(data):
        assert "FAIL_" not in s
        assert "WARN_" not in s
