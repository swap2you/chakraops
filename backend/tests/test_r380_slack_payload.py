# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — Slack-ready payload sanitization."""

from app.core.decision_engine.wheel_v2.contract import WheelDecisionV2
from app.core.decision_engine.wheel_v2.slack_payload import to_slack_ready_payload


def test_slack_payload_structure_and_flags():
    d = WheelDecisionV2(
        symbol="AAPL",
        phase="CSP_ENTRY",
        phase_label="Cash-secured put entry",
        action="OPEN_CSP",
        action_label="Open cash-secured put",
        strategy="CSP",
        manual_plan={
            "summary_label": "Open CSP · AAPL",
            "strike": 180.0,
            "expiry": "2026-12-18",
            "premium": 2.0,
        },
        arbitration={"reason_codes": ["CSP_PREFERRED"], "reason_labels": ["Cash-secured put preferred"]},
        manual_only=True,
        trade_execution=False,
    )
    payload = to_slack_ready_payload(d)
    assert payload["symbol"] == "AAPL"
    assert payload["phase"] == "CSP_ENTRY"
    assert payload["phase_label"]
    assert payload["action"] == "OPEN_CSP"
    assert payload["action_label"]
    assert payload["plan_summary"]
    assert payload["manual_only"] is True
    assert payload["trade_execution"] is False
    assert payload["render_only"] is True


def test_slack_payload_sanitizes_raw_fail_warn():
    payload = to_slack_ready_payload(
        {
            "symbol": "X",
            "phase": "STAY_IN_CASH",
            "action": "STAY_IN_CASH",
            "strategy": "CASH",
            "phase_label": "FAIL_REGIME blocked",
            "action_label": "WARN_STALE review",
            "manual_plan": {"summary_label": "FAIL_DELTA_OUT_OF_RANGE"},
        }
    )
    blob = str(payload)
    assert "FAIL_" not in blob
    assert "WARN_" not in blob
