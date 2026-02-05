# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Why-no-trade explanation engine (Phase 5.1).

Produces a structured explanation when no trades are READY.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

# DecisionSnapshot may be a dataclass or dict (from asdict)
from app.signals.decision_snapshot import DecisionSnapshot


def explain_no_trade(
    decision_snapshot: DecisionSnapshot | Dict[str, Any],
    gate_result: Any = None,
    trade_proposal: Any = None,
) -> Dict[str, Any]:
    """Produce a structured explanation when no trades are READY.

    If any TradeProposal has execution_status == READY, no_trade is false
    and a minimal summary is returned. Otherwise aggregates exclusion/blocking
    reasons and identifies top blocking causes.

    Parameters
    ----------
    decision_snapshot : DecisionSnapshot or dict
        Snapshot from signal engine (stats, exclusions, selected_signals).
    gate_result : optional
        ExecutionGateResult with reasons (list of str). If None, only snapshot exclusions are used.
    trade_proposal : optional
        TradeProposal with execution_status. If READY, no_trade=false.

    Returns
    -------
    dict
        no_trade, summary, primary_reasons, secondary_reasons,
        symbols_considered, symbols_passed_selection, symbols_ready.
    """
    snapshot = _as_dict(decision_snapshot)
    stats = snapshot.get("stats") or {}
    exclusions = snapshot.get("exclusions") or []
    selected_signals = snapshot.get("selected_signals") or []

    symbols_considered = int(stats.get("symbols_evaluated", 0))
    symbols_passed_selection = len(selected_signals)
    symbols_ready = 0

    # Check if any trade is READY
    if trade_proposal is not None:
        status = getattr(trade_proposal, "execution_status", None)
        if status == "READY":
            symbols_ready = 1
    # If trade_proposal is a dict (e.g. from serialized output)
    if isinstance(trade_proposal, dict):
        if trade_proposal.get("execution_status") == "READY":
            symbols_ready = 1

    no_trade = symbols_ready == 0

    # Aggregate reasons by code: from snapshot exclusions (rule) and gate_result.reasons
    code_counts: Counter = Counter()
    for excl in exclusions:
        if isinstance(excl, dict):
            code = excl.get("rule") or excl.get("code") or "UNKNOWN"
            code_counts[code] += 1
    if gate_result is not None:
        reasons = getattr(gate_result, "reasons", None) or []
        if isinstance(reasons, list):
            for r in reasons:
                if isinstance(r, str) and r.strip():
                    code_counts[r.strip()] += 1

    # Top 3 = primary_reasons, rest = secondary_reasons (sorted by count desc)
    sorted_reasons = sorted(
        code_counts.items(),
        key=lambda x: (-x[1], x[0]),
    )
    primary = [{"code": code, "count": count} for code, count in sorted_reasons[:3]]
    secondary = [{"code": code, "count": count} for code, count in sorted_reasons[3:]]

    if no_trade:
        if primary:
            top = primary[0]
            summary = f"No trades met safety criteria today (top blocker: {top['code']})"
        else:
            summary = "No trades met safety criteria today"
    else:
        summary = "At least one trade is READY"

    return {
        "no_trade": no_trade,
        "summary": summary,
        "primary_reasons": primary,
        "secondary_reasons": secondary,
        "symbols_considered": symbols_considered,
        "symbols_passed_selection": symbols_passed_selection,
        "symbols_ready": symbols_ready,
    }


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Convert DecisionSnapshot or dict to dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    return {}
