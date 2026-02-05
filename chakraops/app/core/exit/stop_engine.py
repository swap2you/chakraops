# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Stop engine: evaluates formal exit rules (profit target, max loss, time stop, underlying breach, regime).

Phase 6.3: Only considers OPEN/PARTIALLY_CLOSED positions. When profit or stop thresholds hit,
emits PositionEvent (TARGET_1_HIT, TARGET_2_HIT, STOP_TRIGGERED) and returns ALERT (no auto-close).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List

from app.core.action_engine import ActionDecision
from app.core.models.position import Position
from app.models.exit_plan import ExitPlan

logger = logging.getLogger(__name__)


def _allowed_next_states(position: Position) -> List[str]:
    """Compute allowed next states for the position's current state."""
    current_state = position.state or (getattr(position, "status", None) or "OPEN")
    try:
        from app.core.state_machine import PositionState, get_allowed_actions
        state_mapping = {
            "NEW": PositionState.NEW,
            "ASSIGNED": PositionState.ASSIGNED,
            "OPEN": PositionState.OPEN,
            "ROLLING": PositionState.ROLLING,
            "CLOSING": PositionState.CLOSING,
            "CLOSED": PositionState.CLOSED,
        }
        current_state_enum = state_mapping.get(current_state, PositionState.OPEN)
        allowed_actions = get_allowed_actions(current_state_enum)
        allowed_next_states = [
            "OPEN" if a.value == "OPEN" else
            "CLOSING" if a.value == "CLOSE" else
            "ROLLING" if a.value == "ROLL" else
            current_state
            for a in allowed_actions
        ]
        if any(a.value == "HOLD" for a in allowed_actions):
            allowed_next_states.append(current_state)
        return list(set(allowed_next_states))
    except Exception:
        return ["OPEN", "CLOSING", "ROLLING"]


def evaluate_stop(
    position: Position,
    market_context: Dict[str, Any],
) -> ActionDecision:
    """Evaluate formal exit rules (ExitPlan) and return CLOSE, ROLL, or HOLD.

    Uses option spread value (not just underlying price) where appropriate for
    gaps and bid/ask. Evaluated in order; first match wins:

    1. Profit target: current option value (cost to close) <= credit * (1 - profit_target_pct) -> CLOSE
    2. Max loss: option value >= credit * max_loss_multiplier -> CLOSE
    3. Time stop: DTE <= time_stop_days -> CLOSE
    4. Underlying breach: if underlying_stop_breach and underlying closed beyond short strike -> CLOSE
    5. Regime flip: current regime RISK_OFF (entry assumed RISK_ON) -> CLOSE
    6. Otherwise -> HOLD

    Parameters
    ----------
    position
        Position with optional exit_plan. If no exit_plan, returns HOLD (no formal rules).
    market_context
        Must include:
        - price or underlying_price: current underlying price
        - option_value: total current cost to buy back (close) the position (same units as premium_collected)
        - regime: current regime ("RISK_ON" | "RISK_OFF")
        Optional: dte (int); if missing, computed from position.expiry.

    Returns
    -------
    ActionDecision
        CLOSE with reason, or HOLD. ROLL is not produced by stop rules (handled by action engine).
    """
    symbol = position.symbol
    # Phase 6.3: only evaluate OPEN or PARTIALLY_CLOSED positions
    lifecycle_state = getattr(position, "lifecycle_state", None) or (position.state or "OPEN")
    if lifecycle_state not in ("OPEN", "PARTIALLY_CLOSED"):
        allowed = _allowed_next_states(position)
        return ActionDecision(
            symbol=symbol,
            action="HOLD",
            urgency="LOW",
            reason_codes=["LIFECYCLE_NOT_ACTIVE"],
            explanation=f"Position lifecycle_state={lifecycle_state}; stop rules only apply to OPEN/PARTIALLY_CLOSED.",
            allowed_next_states=allowed,
        )

    exit_plan: ExitPlan | None = getattr(position, "exit_plan", None)
    if exit_plan is None:
        allowed = _allowed_next_states(position)
        return ActionDecision(
            symbol=symbol,
            action="HOLD",
            urgency="LOW",
            reason_codes=["NO_EXIT_PLAN"],
            explanation="No formal exit plan; skip stop rules.",
            allowed_next_states=allowed,
        )

    credit = getattr(position, "entry_credit", None) or position.premium_collected
    if credit <= 0:
        allowed = _allowed_next_states(position)
        return ActionDecision(
            symbol=symbol,
            action="HOLD",
            urgency="LOW",
            reason_codes=["NO_CREDIT"],
            explanation="Position has no credit; skip stop rules.",
            allowed_next_states=allowed,
        )

    # DTE
    dte = market_context.get("dte")
    if dte is None and position.expiry:
        try:
            if isinstance(position.expiry, str) and len(position.expiry) == 10:
                expiry_date = date.fromisoformat(position.expiry)
            else:
                expiry_date = datetime.fromisoformat(position.expiry).date()
            dte = (expiry_date - date.today()).days
        except (ValueError, AttributeError, TypeError):
            dte = None

    price = market_context.get("price") or market_context.get("underlying_price")
    option_value = market_context.get("option_value")  # total cost to close
    regime = (market_context.get("regime") or "").upper()

    allowed = _allowed_next_states(position)

    # Phase 6.3: emit PositionEvent and return ALERT (do not auto-close); surface as alert signal
    def _emit_and_alert(event_type: str, reason_codes: List[str], urgency: str, explanation: str) -> ActionDecision:
        try:
            from app.core.persistence import add_position_event
            add_position_event(
                position.id,
                event_type,
                metadata={"symbol": symbol, "reason_codes": reason_codes, "explanation": explanation},
            )
        except Exception as e:
            logger.warning("Failed to emit position event: %s", e)
        return ActionDecision(
            symbol=symbol,
            action="ALERT",
            urgency=urgency,
            reason_codes=reason_codes,
            explanation=explanation,
            allowed_next_states=allowed,
        )

    # 1. Profit target: emit TARGET_1_HIT / TARGET_2_HIT and ALERT (no auto-close)
    if option_value is not None:
        target_close = credit * (1.0 - exit_plan.profit_target_pct)
        if option_value <= target_close:
            return _emit_and_alert(
                "TARGET_1_HIT",
                ["PROFIT_TARGET"],
                "MEDIUM",
                (
                    f"Profit target met: option value {option_value:.2f} <= "
                    f"target {target_close:.2f} (credit*(1-{exit_plan.profit_target_pct}))"
                ),
            )

        # 2. Max loss: emit STOP_TRIGGERED and ALERT (no auto-close)
        loss_threshold = credit * exit_plan.max_loss_multiplier
        if option_value >= loss_threshold:
            return _emit_and_alert(
                "STOP_TRIGGERED",
                ["MAX_LOSS"],
                "HIGH",
                (
                    f"Max loss hit: option value {option_value:.2f} >= "
                    f"threshold {loss_threshold:.2f} (credit*{exit_plan.max_loss_multiplier})"
                ),
            )

    # 3. Time stop: emit STOP_TRIGGERED and ALERT
    if dte is not None and exit_plan.time_stop_days is not None and dte <= exit_plan.time_stop_days:
        return _emit_and_alert(
            "STOP_TRIGGERED",
            ["TIME_STOP"],
            "HIGH",
            f"Time stop: DTE {dte} <= {exit_plan.time_stop_days} days.",
        )

    # 4. Underlying breach: emit STOP_TRIGGERED and ALERT
    if exit_plan.underlying_stop_breach and price is not None and position.strike is not None:
        is_csp = (position.position_type or "").upper() == "CSP"
        if is_csp and price < position.strike:
            return _emit_and_alert(
                "STOP_TRIGGERED",
                ["UNDERLYING_BREACH"],
                "HIGH",
                f"Underlying closed below short strike: price {price:.2f} < strike {position.strike:.2f}.",
            )
        if not is_csp and price > position.strike:
            return _emit_and_alert(
                "STOP_TRIGGERED",
                ["UNDERLYING_BREACH"],
                "HIGH",
                f"Underlying closed above short strike: price {price:.2f} > strike {position.strike:.2f}.",
            )

    # 5. Regime flip: emit STOP_TRIGGERED and ALERT
    if regime == "RISK_OFF":
        return _emit_and_alert(
            "STOP_TRIGGERED",
            ["REGIME_FLIP"],
            "HIGH",
            "Regime flipped to RISK_OFF; exit per exit plan.",
        )

    return ActionDecision(
        symbol=symbol,
        action="HOLD",
        urgency="LOW",
        reason_codes=["STOP_RULES_OK"],
        explanation="No stop/exit trigger; position within exit plan.",
        allowed_next_states=allowed,
    )


__all__ = ["evaluate_stop"]
