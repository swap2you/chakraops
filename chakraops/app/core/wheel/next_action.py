# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 18.0: Wheel next action engine — compute suggested action from state, decision, risk.
   Phase 19.0: Wheel policy — BLOCKED when policy blocks."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ACTION_TYPES = frozenset({"OPEN_TICKET", "ROLL", "HOLD", "REASSIGN", "BLOCKED", "NONE"})


def compute_next_action(
    symbol: str,
    wheel_state: Dict[str, Any],
    latest_decision_artifact: Optional[Any],
    portfolio_risk: Dict[str, Any],
    *,
    account: Optional[Any] = None,
    open_positions: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Compute next suggested action for a symbol.
    Returns {action_type, suggested_contract_key, reasons[], blocked_by[]}.
    BLOCKED if portfolio_risk status is FAIL or wheel policy blocks (Phase 19.0).
    """
    symbol = (symbol or "").strip().upper()
    state = (wheel_state.get("state") or "EMPTY").upper()
    risk_status = (portfolio_risk.get("status") or "PASS").upper()
    blocked_by: List[str] = []
    reasons: List[str] = []

    if risk_status == "FAIL":
        blocked_by.append("portfolio_risk_FAIL")
        return {
            "action_type": "BLOCKED",
            "suggested_contract_key": None,
            "reasons": ["Portfolio risk limit breach."],
            "blocked_by": blocked_by,
        }

    # Get candidate from decision artifact (for suggested_contract_key and expiry for policy)
    suggested_contract_key: Optional[str] = None
    candidate_expiry: Optional[str] = None
    if latest_decision_artifact and hasattr(latest_decision_artifact, "candidates_by_symbol"):
        candidates = latest_decision_artifact.candidates_by_symbol.get(symbol) or []
        if candidates:
            c = candidates[0]
            suggested_contract_key = getattr(c, "contract_key", None) or (c.get("contract_key") if isinstance(c, dict) else None)
            candidate_expiry = getattr(c, "expiry", None) or getattr(c, "expiration", None) or (c.get("expiry") or c.get("expiration")) if isinstance(c, dict) else None

    # Phase 19.0: Wheel policy — block OPEN_TICKET/REASSIGN when policy fails
    if account and open_positions is not None and state in ("EMPTY", "ASSIGNED", "CLOSED"):
        from app.core.wheel.policy import evaluate_wheel_policy
        policy_result = evaluate_wheel_policy(
            account, symbol, wheel_state, latest_decision_artifact, open_positions,
            expiration=candidate_expiry, contract_key=suggested_contract_key,
        )
        if not policy_result.get("allowed"):
            blocked_by.extend(policy_result.get("blocked_by") or [])
            if blocked_by:
                return {
                    "action_type": "BLOCKED",
                    "suggested_contract_key": suggested_contract_key,
                    "reasons": ["Wheel policy: " + "; ".join(policy_result.get("blocked_by") or [])],
                    "blocked_by": blocked_by,
                }

    if state == "EMPTY":
        if suggested_contract_key:
            reasons.append("Symbol eligible in decision; no position.")
            return {
                "action_type": "OPEN_TICKET",
                "suggested_contract_key": suggested_contract_key,
                "reasons": reasons,
                "blocked_by": blocked_by,
            }
        reasons.append("No position; no eligible candidate in decision.")
        return {"action_type": "NONE", "suggested_contract_key": None, "reasons": reasons, "blocked_by": blocked_by}

    if state == "ASSIGNED":
        reasons.append("Assigned; open ticket when ready.")
        return {
            "action_type": "OPEN_TICKET",
            "suggested_contract_key": suggested_contract_key,
            "reasons": reasons,
            "blocked_by": blocked_by,
        }

    if state == "OPEN":
        reasons.append("Position open; monitor for roll/exit.")
        return {"action_type": "HOLD", "suggested_contract_key": None, "reasons": reasons, "blocked_by": blocked_by}

    if state == "CLOSED":
        if suggested_contract_key:
            reasons.append("Closed; eligible for reassignment.")
            return {
                "action_type": "REASSIGN",
                "suggested_contract_key": suggested_contract_key,
                "reasons": reasons,
                "blocked_by": blocked_by,
            }
        return {"action_type": "NONE", "suggested_contract_key": None, "reasons": reasons, "blocked_by": blocked_by}

    return {"action_type": "NONE", "suggested_contract_key": None, "reasons": reasons, "blocked_by": blocked_by}
