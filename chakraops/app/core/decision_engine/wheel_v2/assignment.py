# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 assignment advisory — next phase after (potential) assignment."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union

from app.core.decision_engine.wheel_v2.contract import OwnabilityResult
from app.core.decision_engine.wheel_v2.phases import WheelPhase


def assignment_advisory(
    *,
    shares_held: int = 0,
    contracts: int = 1,
    will_assign: bool = True,
    ownability: Optional[Union[OwnabilityResult, Mapping[str, Any]]] = None,
    strategy: str = "CSP",
) -> Dict[str, Any]:
    """
    Assignment advisory + next-phase suggestion.

    - If shares ≥ 100 (or will be after assign of 100*contracts) and ownable → CC_ENTRY
    - If not ownable → EXIT (or HOLD if not assigning)
    - Otherwise EXIT / HOLD as appropriate
    """
    contracts_i = max(int(contracts or 1), 0)
    shares_now = max(int(shares_held or 0), 0)
    shares_after = shares_now + (100 * contracts_i if will_assign and (strategy or "").upper() == "CSP" else 0)

    ownable = True
    own_codes = []
    if ownability is not None:
        if isinstance(ownability, OwnabilityResult):
            ownable = ownability.ownable
            own_codes = list(ownability.reason_codes)
        elif isinstance(ownability, Mapping):
            ownable = bool(ownability.get("ownable", False))
            own_codes = list(ownability.get("reason_codes") or [])

    enough_for_cc = shares_after >= 100

    if will_assign and enough_for_cc and ownable:
        next_phase = WheelPhase.CC_ENTRY.value
        action = "PREPARE_CC"
        reason_codes = ["ASSIGNMENT_TO_CC"] + own_codes
    elif will_assign and enough_for_cc and not ownable:
        next_phase = WheelPhase.EXIT.value
        action = "EXIT_SHARES"
        reason_codes = ["ASSIGNMENT_INAPPROPRIATE"] + own_codes
    elif will_assign and not enough_for_cc:
        next_phase = WheelPhase.EXIT.value
        action = "EXIT_OR_ACCUMULATE"
        reason_codes = ["SHARES_BELOW_CC_LOT"] + own_codes
    else:
        next_phase = WheelPhase.CSP_MANAGE.value if (strategy or "").upper() == "CSP" else WheelPhase.CC_MANAGE.value
        action = "HOLD"
        reason_codes = ["NO_ASSIGNMENT"] + own_codes

    return {
        "will_assign": will_assign,
        "shares_held": shares_now,
        "shares_after_assign": shares_after,
        "enough_for_cc": enough_for_cc,
        "ownable": ownable,
        "next_phase": next_phase,
        "action": action,
        "reason_codes": reason_codes,
        "manual_only": True,
        "trade_execution": False,
    }
