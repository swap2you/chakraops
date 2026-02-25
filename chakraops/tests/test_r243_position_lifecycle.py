# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.3: Position lifecycle (request-time only), action-needed no FAIL_/WARN_, determinism."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.lifecycle.position_lifecycle_r243 import (
    RECOMMENDED_BY,
    MARK_SOURCE_MID,
    MARK_SOURCE_LAST,
    MARK_SOURCE_BID,
    MARK_SOURCE_ASK,
    MARK_SOURCE_UNKNOWN,
    compute_position_lifecycle,
    select_mark_from_quote,
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
    """R24.3/R24.4: Lifecycle fields must not be persisted in decision_latest.json."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2
    import json
    artifact = DecisionArtifactV2(metadata={"run_id": "test"}, symbols=[], selected_candidates=[])
    data = artifact.to_dict_persist()
    json_str = json.dumps(data, default=str)
    assert "assignment_risk" not in json_str
    assert "roll_window" not in json_str
    assert "mark_value" not in json_str
    assert "mark_source" not in json_str
    assert "roll_reason_codes" not in json_str


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


# R24.4: Mark provenance/freshness + roll rationale
@pytest.mark.parametrize("bid,ask,last,expected_source", [
    (1.0, 1.2, None, MARK_SOURCE_MID),
    (None, None, 1.1, MARK_SOURCE_LAST),
    (1.0, None, 1.1, MARK_SOURCE_LAST),  # LAST before single BID
    (1.0, None, None, MARK_SOURCE_BID),
    (None, 1.2, None, MARK_SOURCE_ASK),
    (None, None, None, MARK_SOURCE_UNKNOWN),
])
def test_r244_select_mark_deterministic(bid, ask, last, expected_source):
    """R24.4: Deterministic mark selection order MID -> LAST -> BID -> ASK -> UNKNOWN."""
    val, src, qts, age = select_mark_from_quote(bid=bid, ask=ask, last=last)
    assert src == expected_source
    if expected_source != MARK_SOURCE_UNKNOWN:
        assert val is not None


def test_r244_mark_age_sec_from_quote_ts():
    """R24.4: mark_age_sec computed from quote_ts and as_of_ts."""
    import time
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(seconds=18)).isoformat().replace("+00:00", "Z")
    as_of = time.time()
    _, _, _, age = select_mark_from_quote(bid=1.0, ask=1.1, quote_ts=past, as_of_ts=as_of)
    assert age is not None
    assert 15 <= age <= 25


def test_r244_roll_rationale_when_roll():
    """R24.4: When recommended_action_code is ROLL, roll_window_threshold_dte and roll_reason_codes present."""
    pos = _MockPosition(expiration="2026-03-01")  # DTE <= 14
    out = compute_position_lifecycle(pos, mark_proxy=1.5, profit_target_pct=90.0)
    assert out["recommended_action_code"] == "ROLL"
    assert out.get("roll_window_threshold_dte") == ROLL_WINDOW_DTE_DEFAULT
    assert out.get("roll_reason_codes") == ["DTE_WINDOW"]


def test_r244_lifecycle_with_quote_outputs_mark_provenance():
    """R24.4: With bid/ask/quote_ts/as_of_ts, output includes mark_value, mark_source, mark_age_sec."""
    pos = _MockPosition(open_credit=2.0)
    import time
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    out = compute_position_lifecycle(pos, bid=0.8, ask=0.9, quote_ts=past, as_of_ts=time.time())
    assert out["mark_value"] is not None
    assert out["mark_source"] == MARK_SOURCE_MID
    assert out.get("mark_age_sec") is not None
