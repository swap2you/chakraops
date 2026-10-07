# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R39: Thin Slack formatter for wheel_v2 slack_payload (render-only; no decisions).

Consumes the structured dict from ``to_slack_ready_payload`` and produces a
state-change focused Slack text. Does not evaluate strategy, size, or eligibility.
Dedupe is left to callers via ``should_send_actionable_message`` / ``should_send_alert``.
Does not enable any scheduler.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from app.core.alerts.slack_dispatcher import (
    FORBIDDEN_IN_SLACK,
    _sanitize_slack_text,
    should_send_actionable_message,
)


def format_wheel_v2_slack_message(slack_payload: Mapping[str, Any]) -> str:
    """
    Render-only formatter. Input must already be a wheel_v2 ``slack_payload``
    (or compatible mapping). Never invents financial fields or decisions.
    """
    symbol = str(slack_payload.get("symbol") or "?").strip() or "?"
    phase_label = str(slack_payload.get("phase_label") or slack_payload.get("phase") or "").strip()
    action_label = str(slack_payload.get("action_label") or slack_payload.get("action") or "No action").strip()
    strategy = str(slack_payload.get("strategy") or "").strip()
    plan_summary = str(slack_payload.get("plan_summary") or "").strip()
    arb = slack_payload.get("arbitration_labels") or []

    lines = [
        "*Wheel advisory (state change)*",
        "Symbol: %s" % symbol,
    ]
    if phase_label:
        lines.append("Phase: %s" % phase_label)
    if strategy:
        lines.append("Strategy: %s" % strategy)
    lines.append("Action: %s" % action_label)
    if plan_summary and plan_summary != "No plan details":
        lines.append("Plan: %s" % plan_summary)
    if isinstance(arb, list):
        for label in arb[:3]:
            if isinstance(label, str) and label and not any(f in label for f in FORBIDDEN_IN_SLACK):
                lines.append("• %s" % label)
    lines.append("Manual execution only — no orders placed.")
    return _sanitize_slack_text("\n".join(lines))


def wheel_v2_dedupe_parts(slack_payload: Mapping[str, Any]) -> Tuple[str, str, str, Optional[str], Optional[str]]:
    """Extract (symbol, strategy, action, contract_key, size) for actionable dedupe."""
    symbol = str(slack_payload.get("symbol") or "").strip()
    strategy = str(slack_payload.get("strategy") or "WHEEL").strip() or "WHEEL"
    action = str(slack_payload.get("action") or "NONE").strip() or "NONE"
    return symbol, strategy, action, None, None


def should_send_wheel_v2_slack(
    slack_payload: Mapping[str, Any],
    *,
    severity: str = "normal",
    state_path: Any = None,
    throttle_minutes: Optional[int] = None,
) -> bool:
    """
    Preserve R24.1 actionable dedupe for wheel_v2 payloads.
    Returns True if a send is allowed (caller still responsible for POST).
    """
    symbol, strategy, action, contract_key, size = wheel_v2_dedupe_parts(slack_payload)
    return should_send_actionable_message(
        symbol,
        strategy,
        action,
        contract_key,
        size,
        severity=severity,
        state_path=state_path,
        throttle_minutes=throttle_minutes,
    )


def prepare_wheel_v2_slack_send(
    slack_payload: Mapping[str, Any],
    *,
    severity: str = "normal",
    state_path: Any = None,
    throttle_minutes: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    If dedupe allows, return ``{"text": ..., "manual_only": True, "render_only": True}``.
    Otherwise return None (suppressed). Does not send; no scheduler.
    """
    if not should_send_wheel_v2_slack(
        slack_payload,
        severity=severity,
        state_path=state_path,
        throttle_minutes=throttle_minutes,
    ):
        return None
    text = format_wheel_v2_slack_message(slack_payload)
    return {
        "text": text,
        "manual_only": True,
        "render_only": True,
        "trade_execution": False,
        "channel_hint": "signals",
    }


__all__ = [
    "format_wheel_v2_slack_message",
    "wheel_v2_dedupe_parts",
    "should_send_wheel_v2_slack",
    "prepare_wheel_v2_slack_send",
]
