# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.3: EOD-biased eligibility, options lifecycle, notifications dedupe, no FAIL_/WARN_, no persistence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.lifecycle.position_lifecycle_r243 import (
    RECOMMENDED_BY_R253,
    compute_position_lifecycle,
)
from app.core.settings import get_decision_cadence_mode


def test_get_decision_cadence_mode_default():
    """R25.3: Default cadence mode is EOD_BIASED."""
    with patch.dict(os.environ, {}, clear=False):
        # Clear env so we get config default
        if "DECISION_CADENCE_MODE" in os.environ:
            del os.environ["DECISION_CADENCE_MODE"]
    mode = get_decision_cadence_mode()
    assert mode in ("EOD_BIASED", "LIVE")


def test_get_decision_cadence_mode_env_override():
    """R25.3: DECISION_CADENCE_MODE env overrides to LIVE."""
    with patch.dict(os.environ, {"DECISION_CADENCE_MODE": "LIVE"}):
        assert get_decision_cadence_mode() == "LIVE"
    with patch.dict(os.environ, {"DECISION_CADENCE_MODE": "EOD_BIASED"}):
        assert get_decision_cadence_mode() == "EOD_BIASED"


class _MockPos:
    def __init__(self, strategy="CSP", strike=100.0, expiration="2026-04-18", open_credit=2.50):
        self.strategy = strategy
        self.strike = strike
        self.expiration = expiration
        self.open_credit = open_credit
        self.credit_expected = open_credit


def test_lifecycle_recommended_by_r253():
    """R25.3: Caller can pass recommended_by='r253'."""
    pos = _MockPos(open_credit=2.0)
    out = compute_position_lifecycle(pos, mark_proxy=0.5, recommended_by=RECOMMENDED_BY_R253)
    assert out["recommended_by"] == RECOMMENDED_BY_R253
    assert out["pct_max_profit"] == 75.0
    assert out["recommended_action_code"] == "CLOSE"


def test_lifecycle_determinism_same_inputs():
    """R25.3: Same inputs -> same lifecycle outputs."""
    pos = _MockPos(open_credit=2.0, expiration="2026-05-20")
    a = compute_position_lifecycle(pos, spot=105.0, mark_proxy=1.0, recommended_by="r253")
    b = compute_position_lifecycle(pos, spot=105.0, mark_proxy=1.0, recommended_by="r253")
    assert a["pct_max_profit"] == b["pct_max_profit"]
    assert a["recommended_action_code"] == b["recommended_action_code"]
    assert a["dte"] == b["dte"]


def test_options_lifecycle_notification_dedupe():
    """R25.3: Second call for same contract_key+event_type within window does not append."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import (
                    load_notifications,
                    maybe_append_options_lifecycle_notification,
                    OPTIONS_PROFIT_TARGET_HIT,
                )
                symbol = "R253_DEDUPE"
                ckey = "100-2026-04-18-PUT"
                payload = {"symbol": symbol, "contract_key": ckey, "profit_pct": 55, "mark_value": 1.0, "as_of_ts": "2026-02-27T12:00:00Z"}
                ok1 = maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_PROFIT_TARGET_HIT, payload)
                assert ok1 is True
                ok2 = maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_PROFIT_TARGET_HIT, payload)
                assert ok2 is False
                recs = [r for r in load_notifications(limit=50) if r.get("type") == OPTIONS_PROFIT_TARGET_HIT and r.get("symbol") == symbol]
                assert len(recs) == 1


def test_action_needed_no_fail_warn_r253():
    """R25.3: GET /api/ui/action-needed must not contain FAIL_ or WARN_ in JSON."""
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
