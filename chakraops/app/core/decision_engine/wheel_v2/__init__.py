# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Wheel & Share Decision Engine V2.

Advisory lifecycle: ownability → CSP/shares arbitration → management →
assignment → CC → exit. Always ``manual_only=True`` / ``trade_execution=False``.
Request-time only — never persist prose into ``decision_latest.json``.
"""

from app.core.decision_engine.wheel_v2.phases import WheelPhase, phase_label
from app.core.decision_engine.wheel_v2.contract import (
    OwnabilityResult,
    ManualPlan,
    ArbitrationResult,
    WheelDecisionV2,
    CSP_PREFERRED,
    SHARES_PREFERRED,
    BOTH_UNATTRACTIVE,
    CASH_INSUFFICIENT,
    ASSIGNMENT_INAPPROPRIATE,
)
from app.core.decision_engine.wheel_v2.ownability import evaluate_ownability
from app.core.decision_engine.wheel_v2.management import manage_open_option
from app.core.decision_engine.wheel_v2.assignment import assignment_advisory
from app.core.decision_engine.wheel_v2.arbitration import arbitrate_csp_vs_shares
from app.core.decision_engine.wheel_v2.shares_v2 import build_shares_plan_v2
from app.core.decision_engine.wheel_v2.manual_plan import build_manual_plan
from app.core.decision_engine.wheel_v2.slack_payload import to_slack_ready_payload, action_label
from app.core.decision_engine.wheel_v2.orchestrator import evaluate_wheel_v2

__all__ = [
    "WheelPhase",
    "phase_label",
    "OwnabilityResult",
    "ManualPlan",
    "ArbitrationResult",
    "WheelDecisionV2",
    "CSP_PREFERRED",
    "SHARES_PREFERRED",
    "BOTH_UNATTRACTIVE",
    "CASH_INSUFFICIENT",
    "ASSIGNMENT_INAPPROPRIATE",
    "evaluate_ownability",
    "manage_open_option",
    "assignment_advisory",
    "arbitrate_csp_vs_shares",
    "build_shares_plan_v2",
    "build_manual_plan",
    "to_slack_ready_payload",
    "action_label",
    "evaluate_wheel_v2",
]
