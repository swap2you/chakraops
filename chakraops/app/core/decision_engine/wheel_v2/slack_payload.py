# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Slack-ready payload — structured dict for render-only Slack (no persistence)."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Union

from app.core.decision_engine.wheel_v2.contract import WheelDecisionV2, ARBITRATION_LABELS
from app.core.decision_engine.wheel_v2.phases import phase_label

_RAW_STATUS = re.compile(r"\b(FAIL_|WARN_|PASS_)\w*", re.IGNORECASE)


def _sanitize(text: Optional[str]) -> str:
    """Strip raw FAIL_/WARN_/PASS_ tokens from UI-facing strings."""
    if not text:
        return ""
    s = str(text)
    s = _RAW_STATUS.sub("Review", s)
    # Also strip bare FAIL/WARN/PASS tokens when they appear as status words.
    s = re.sub(r"\bFAIL\b", "Blocked", s, flags=re.IGNORECASE)
    s = re.sub(r"\bWARN\b", "Degraded", s, flags=re.IGNORECASE)
    return s.strip()


_ACTION_LABELS = {
    "HOLD": "Hold",
    "CLOSE": "Close",
    "ROLL": "Roll",
    "OPEN_CSP": "Open cash-secured put",
    "OPEN_CC": "Open covered call",
    "OPEN_SHARES": "Open shares",
    "STAY_IN_CASH": "Stay in cash",
    "PREPARE_CC": "Prepare covered call",
    "EXIT_SHARES": "Exit shares",
    "EXIT_OR_ACCUMULATE": "Exit or accumulate",
    "WATCH": "Watch",
    "NONE": "No action",
}


def action_label(action: Optional[str]) -> str:
    a = (action or "NONE").upper()
    return _ACTION_LABELS.get(a, _sanitize(a.replace("_", " ").title()) or "Advisory")


def to_slack_ready_payload(
    decision: Union[WheelDecisionV2, Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Structured dict for render-only Slack. Includes phase, symbol, strategy,
    action, plan summary, manual_only. Labels are sanitized (no raw FAIL_/WARN_).
    """
    if isinstance(decision, WheelDecisionV2):
        d = decision.to_dict()
    else:
        d = dict(decision)

    phase = d.get("phase") or ""
    action = d.get("action") or "NONE"
    plan = d.get("manual_plan") or {}
    arb = d.get("arbitration") or {}

    plan_summary_parts = []
    if isinstance(plan, Mapping):
        if plan.get("summary_label"):
            plan_summary_parts.append(_sanitize(str(plan["summary_label"])))
        else:
            for key, label in (
                ("strike", "Strike"),
                ("expiry", "Expiry"),
                ("dte", "DTE"),
                ("premium", "Premium"),
                ("breakeven", "Breakeven"),
                ("collateral", "Collateral"),
            ):
                if plan.get(key) is not None:
                    plan_summary_parts.append(f"{label} {plan[key]}")
    plan_summary = " · ".join(plan_summary_parts) if plan_summary_parts else "No plan details"

    reason_labels = []
    if isinstance(arb, Mapping):
        for c in arb.get("reason_codes") or []:
            reason_labels.append(ARBITRATION_LABELS.get(str(c), "Review"))
        if arb.get("reason_labels"):
            reason_labels = [_sanitize(x) for x in arb["reason_labels"]]

    return {
        "symbol": _sanitize(str(d.get("symbol") or "")),
        "phase": phase,
        "phase_label": _sanitize(d.get("phase_label") or phase_label(phase)),
        "strategy": _sanitize(str(d.get("strategy") or "")),
        "action": action,
        "action_label": _sanitize(d.get("action_label") or action_label(action)),
        "plan_summary": _sanitize(plan_summary),
        "arbitration_labels": reason_labels,
        "manual_only": True,
        "trade_execution": False,
        "render_only": True,
    }
