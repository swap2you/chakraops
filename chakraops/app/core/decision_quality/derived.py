# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Derived outcome metrics. Phase 5: Explicit R (risk_amount_at_entry); no inference."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.portfolio.service import _capital_for_position


# Outcome tagging rules (MANDATORY) — only when R is explicitly defined
# WIN: ≥ +0.5R
# SCRATCH: −0.2R to +0.5R
# LOSS: ≤ −0.2R
# R = return_on_risk = realized_pnl / risk_amount (1R = explicit risk at entry)
# Phase 5: If risk_amount_at_entry is missing or <= 0, return_on_risk = null, outcome_tag = null


def outcome_tag_from_return_on_risk(return_on_risk: float) -> str:
    """Compute outcome_tag from return_on_risk (R). Deterministic."""
    if return_on_risk >= 0.5:
        return "WIN"
    if return_on_risk > -0.2:
        return "SCRATCH"
    return "LOSS"


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Parse YYYY-MM-DD or ISO datetime."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 else s, "%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def _days_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    """Days between two date strings. Returns None if either invalid."""
    d1 = _parse_date(start)
    d2 = _parse_date(end)
    if d1 is None or d2 is None:
        return None
    delta = d2 - d1
    return max(0, delta.days)


def compute_derived_metrics(
    position: Any,
    final_exit_record: Any,
    aggregated_realized_pnl: Optional[float] = None,
    capital: Optional[float] = None,
    risk_amount: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute derived metrics from position + final exit. Do not store.

    Phase 5:
    - Uses aggregated_realized_pnl (sum of all exit events) if provided.
    - return_on_risk ONLY when risk_amount is explicitly defined (> 0).
    - If risk_amount missing or <= 0: return_on_risk = null, outcome_tag = null,
      return_on_risk_status = "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"
    """
    result: Dict[str, Any] = {
        "time_in_trade_days": None,
        "capital_days_used": None,
        "return_on_capital": None,
        "return_on_risk": None,
        "return_on_risk_status": "UNKNOWN_INSUFFICIENT_RISK_DEFINITION",
        "outcome_tag": None,
    }
    if not position or not final_exit_record:
        return result

    opened_at = getattr(position, "opened_at", None)
    exit_date = getattr(final_exit_record, "exit_date", None)
    realized_pnl = aggregated_realized_pnl if aggregated_realized_pnl is not None else float(
        getattr(final_exit_record, "realized_pnl", 0)
    )

    days = _days_between(opened_at, exit_date)
    if days is not None:
        result["time_in_trade_days"] = days

    if capital is None:
        capital = _capital_for_position(position)
    if capital <= 0:
        capital = 1.0

    if days is not None:
        result["capital_days_used"] = capital * days

    if capital > 0:
        result["return_on_capital"] = round(realized_pnl / capital, 4)

    # Phase 5: return_on_risk ONLY when risk_amount explicitly defined. Do NOT infer.
    if risk_amount is None:
        risk_amount = getattr(position, "risk_amount_at_entry", None)
    if risk_amount is not None and float(risk_amount) > 0:
        r = round(realized_pnl / float(risk_amount), 4)
        result["return_on_risk"] = r
        result["return_on_risk_status"] = "KNOWN"
        result["outcome_tag"] = outcome_tag_from_return_on_risk(r)
    else:
        result["return_on_risk"] = None
        result["outcome_tag"] = None

    return result
