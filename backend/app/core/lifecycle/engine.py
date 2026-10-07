# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2C: Lifecycle engine — evaluate position lifecycle from targets, eval, regime."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.lifecycle.models import (
    LifecycleAction,
    LifecycleEvent,
    LifecycleState,
    ExitReason,
)
from app.core.positions.models import Position

logger = logging.getLogger(__name__)


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _get_symbol_price_from_eval(eval_snapshot: Any, symbol: str) -> Optional[float]:
    """Extract spot price for symbol from evaluation run symbols list."""
    if not eval_snapshot or not hasattr(eval_snapshot, "symbols"):
        return None
    sym_upper = (symbol or "").strip().upper()
    for s in (eval_snapshot.symbols or []):
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            return _safe_float(s.get("price"))
    return None


def _get_symbol_verdict_from_eval(eval_snapshot: Any, symbol: str) -> Optional[str]:
    """Extract verdict for symbol from evaluation run."""
    if not eval_snapshot or not hasattr(eval_snapshot, "symbols"):
        return None
    sym_upper = (symbol or "").strip().upper()
    for s in (eval_snapshot.symbols or []):
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            return (s.get("verdict") or "").strip() or None
    return None


def _is_data_unreliable(eval_snapshot: Any, symbol: str) -> bool:
    """True if symbol has data health failure (low completeness, missing price).
    BLOCKED is regime-related, not data — handled by _regime_allows_symbol."""
    if not eval_snapshot or not hasattr(eval_snapshot, "symbols"):
        return True
    sym_upper = (symbol or "").strip().upper()
    for s in (eval_snapshot.symbols or []):
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            verdict = (s.get("verdict") or "").strip()
            if verdict in ("DATA_INCOMPLETE", "DATA_INCOMPLETE_FATAL"):
                return True
            completeness = _safe_float(s.get("data_completeness"), 1.0)
            if completeness is not None and completeness < 0.5:
                return True
            if s.get("price") is None and s.get("stockPrice") is None:
                return True
            return False
    # Symbol not in eval run — data unreliable for lifecycle
    return True


def _regime_allows_symbol(regime: str, symbol_explain: Dict[str, Any]) -> bool:
    """
    True if current regime allows holding this symbol.
    Regime flip disallowed = regime no longer permits this position.
    If regime is empty or symbol_explain has no regime gate, assume allowed.
    """
    if not regime or not symbol_explain:
        return True
    verdict = (symbol_explain.get("verdict") or "").strip()
    if verdict in ("ELIGIBLE", "SHORTLIST", "HOLD"):
        return True
    if verdict in ("BLOCKED", "DATA_INCOMPLETE", "DATA_INCOMPLETE_FATAL"):
        return False
    # ELIGIBLE/HOLD = allowed; BLOCKED = regime break
    return verdict != "BLOCKED"


def evaluate_position_lifecycle(
    position: Position,
    symbol_explain: Dict[str, Any],
    symbol_targets: Dict[str, Any],
    latest_eval_snapshot: Any,
    eval_run_id: str = "",
) -> List[LifecycleEvent]:
    """
    Evaluate position lifecycle and return directive events.

    Rules:
    - Target1 hit → directive: "EXIT 1 CONTRACT" (SCALE_OUT)
    - Target2 hit → directive: "EXIT ALL REMAINING" (EXIT)
    - Stop hit → directive: "EXIT IMMEDIATELY (STOP LOSS)" (EXIT, STOP_LOSS)
    - Regime flips disallowed → directive: "ABORT POSITION" (ABORT)
    - Data health failure → directive: "HOLD — DATA UNRELIABLE" (HOLD)

    Targets: entry_low, entry_high, stop, target1, target2 (underlying price levels).
    For CSP: stop < current < target1 < target2 typically.
    - price < stop → stop loss
    - price >= target1 (and OPEN) → scale out 1 contract
    - price >= target2 → exit all
    """
    events: List[LifecycleEvent] = []
    sym = (position.symbol or "").strip().upper()
    pos_id = position.position_id or ""
    status = (position.status or "OPEN").strip()

    # Only evaluate OPEN or PARTIAL_EXIT positions
    if status not in ("OPEN", "PARTIAL_EXIT"):
        return events

    price = _get_symbol_price_from_eval(latest_eval_snapshot, sym)
    stop = _safe_float(symbol_targets.get("stop"))
    target1 = _safe_float(symbol_targets.get("target1"))
    target2 = _safe_float(symbol_targets.get("target2"))

    has_targets = (target1 is not None) or (target2 is not None)
    has_stop = stop is not None
    if not has_targets and not has_stop:
        return events

    # Data health failure → HOLD
    if _is_data_unreliable(latest_eval_snapshot, sym):
        events.append(LifecycleEvent(
            position_id=pos_id,
            symbol=sym,
            lifecycle_state=LifecycleState.OPEN if status == "OPEN" else LifecycleState.PARTIAL_EXIT,
            action=LifecycleAction.HOLD,
            reason=ExitReason.DATA_FAILURE,
            directive="HOLD — DATA UNRELIABLE",
            eval_run_id=eval_run_id,
            meta={"price": price},
        ))
        return events

    regime = getattr(latest_eval_snapshot, "regime", None) or ""
    if not _regime_allows_symbol(regime, symbol_explain):
        events.append(LifecycleEvent(
            position_id=pos_id,
            symbol=sym,
            lifecycle_state=LifecycleState.ABORTED,
            action=LifecycleAction.ABORT,
            reason=ExitReason.REGIME_BREAK,
            directive="ABORT POSITION",
            eval_run_id=eval_run_id,
            meta={"regime": regime, "verdict": symbol_explain.get("verdict")},
        ))
        return events

    if price is None:
        return events

    # Stop hit → EXIT IMMEDIATELY (highest priority)
    if stop is not None and price <= stop:
        events.append(LifecycleEvent(
            position_id=pos_id,
            symbol=sym,
            lifecycle_state=LifecycleState.CLOSED,
            action=LifecycleAction.EXIT,
            reason=ExitReason.STOP_LOSS,
            directive="EXIT IMMEDIATELY (STOP LOSS)",
            eval_run_id=eval_run_id,
            meta={"price": price, "stop": stop},
        ))
        return events

    # Target2 hit → EXIT ALL REMAINING
    if target2 is not None and price >= target2:
        events.append(LifecycleEvent(
            position_id=pos_id,
            symbol=sym,
            lifecycle_state=LifecycleState.CLOSED,
            action=LifecycleAction.EXIT,
            reason=ExitReason.TARGET_2,
            directive="EXIT ALL REMAINING",
            eval_run_id=eval_run_id,
            meta={"price": price, "target2": target2},
        ))
        return events

    # Target1 hit → EXIT 1 CONTRACT (scale out)
    if target1 is not None and price >= target1 and status == "OPEN":
        events.append(LifecycleEvent(
            position_id=pos_id,
            symbol=sym,
            lifecycle_state=LifecycleState.PARTIAL_EXIT,
            action=LifecycleAction.SCALE_OUT,
            reason=ExitReason.TARGET_1,
            directive="EXIT 1 CONTRACT",
            eval_run_id=eval_run_id,
            meta={"price": price, "target1": target1},
        ))
        return events

    # Target1 hit when already PARTIAL_EXIT → maybe target2 next; if target2 not set, treat as exit remaining
    if target1 is not None and price >= target1 and status == "PARTIAL_EXIT":
        if target2 is not None:
            # Wait for target2
            pass
        else:
            events.append(LifecycleEvent(
                position_id=pos_id,
                symbol=sym,
                lifecycle_state=LifecycleState.CLOSED,
                action=LifecycleAction.EXIT,
                reason=ExitReason.TARGET_2,
                directive="EXIT ALL REMAINING",
                eval_run_id=eval_run_id,
                meta={"price": price, "target1": target1},
            ))

    return events
