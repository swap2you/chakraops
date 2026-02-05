# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Daily and weekly trust reports (Phase 5.3).

Human-readable summaries of system behavior: trades considered, rejected, READY,
capital protected estimate, top blocking reasons.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from app.core.observability.rejection_analytics import summarize_rejections
from app.core.observability.why_no_trade import explain_no_trade


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Convert snapshot or dict to dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    return {}


def generate_daily_report(
    decision_snapshot: Any,
    gate_result: Any = None,
    trade_proposal: Any = None,
    *,
    as_of: Optional[str] = None,
    run_mode: Optional[str] = None,
    config_frozen: Optional[bool] = None,
    freeze_violation_changed_keys: Optional[List[str]] = None,
    capital_deployed_today: Optional[float] = None,
    month_to_date_realized_pnl: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate a daily trust report from a decision snapshot (and optional gate/proposal).

    Includes:
    - trades_considered: symbols evaluated / candidates considered
    - trades_rejected: total rejections (exclusions + gate blocks)
    - trades_ready: 1 if any proposal is READY, else 0
    - capital_protected_estimate: max_loss of blocked proposal (estimate of capital not put at risk)
    - top_blocking_reasons: list of {code, count} (top 5)
    - run_mode: DRY_RUN | PAPER_LIVE | LIVE (Phase 6.1)
    - config_frozen: YES/NO for observability (Phase 6.1)
    - freeze_violation_changed_keys: if freeze violated, list of changed keys (Phase 6.1)
    - capital_deployed_today: sum of OPEN credit today (Phase 6.4)
    - month_to_date_realized_pnl: MTD realized pnl from ledger (Phase 6.4)

    Parameters
    ----------
    decision_snapshot : dict or DecisionSnapshot
        Snapshot from signal engine.
    gate_result : optional
        ExecutionGateResult with reasons.
    trade_proposal : optional
        TradeProposal (or dict) with execution_status, max_loss.
    as_of : optional
        ISO timestamp or date string for the report.
    run_mode : optional
        Run mode string (Phase 6.1).
    config_frozen : optional
        Whether config was frozen for this run (Phase 6.1).
    freeze_violation_changed_keys : optional
        If freeze violated, list of changed config keys (Phase 6.1).

    Returns
    -------
    dict
        report_type, as_of, trades_considered, trades_rejected, trades_ready,
        capital_protected_estimate, top_blocking_reasons, summary,
        run_mode, config_frozen, freeze_violation_changed_keys (when provided).
    """
    snapshot = _as_dict(decision_snapshot)
    stats = snapshot.get("stats") or {}
    rejection_summary = summarize_rejections(snapshot, gate_result)
    why = explain_no_trade(snapshot, gate_result, trade_proposal)

    trades_considered = int(stats.get("symbols_evaluated", 0)) or int(stats.get("total_candidates", 0))
    trades_rejected = rejection_summary.get("total_rejections", 0)
    trades_ready = why.get("symbols_ready", 0)
    by_reason = rejection_summary.get("by_reason") or {}
    sorted_reasons = sorted(by_reason.items(), key=lambda x: (-x[1], x[0]))[:5]
    top_blocking_reasons = [{"code": code, "count": count} for code, count in sorted_reasons]

    capital_protected_estimate: float = 0.0
    if trade_proposal is not None and trades_ready == 0:
        max_loss = getattr(trade_proposal, "max_loss", None)
        if max_loss is None and isinstance(trade_proposal, dict):
            max_loss = trade_proposal.get("max_loss")
        if max_loss is not None:
            try:
                capital_protected_estimate = float(max_loss)
            except (TypeError, ValueError):
                pass

    summary = why.get("summary", "No summary available.")

    out: Dict[str, Any] = {
        "report_type": "daily",
        "as_of": as_of or "",
        "trades_considered": trades_considered,
        "trades_rejected": trades_rejected,
        "trades_ready": trades_ready,
        "capital_protected_estimate": round(capital_protected_estimate, 2),
        "top_blocking_reasons": top_blocking_reasons,
        "summary": summary,
    }
    if run_mode is not None:
        out["run_mode"] = run_mode
    if config_frozen is not None:
        out["config_frozen"] = config_frozen
    if freeze_violation_changed_keys is not None:
        out["freeze_violation_changed_keys"] = freeze_violation_changed_keys
    if capital_deployed_today is not None:
        out["capital_deployed_today"] = round(capital_deployed_today, 2)
    if month_to_date_realized_pnl is not None:
        out["month_to_date_realized_pnl"] = round(month_to_date_realized_pnl, 2)
    return out


def generate_weekly_report(history: List[Dict[str, Any]], *, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Generate a weekly trust report from a list of daily reports or rejection summaries.

    Aggregates: trades_considered, trades_rejected, trades_ready, capital_protected_estimate;
    merges top_blocking_reasons across the period.

    Parameters
    ----------
    history : list of dicts
        Each dict has trades_considered, trades_rejected, trades_ready,
        capital_protected_estimate, top_blocking_reasons (or by_reason).
    as_of : optional
        End date or timestamp for the report.

    Returns
    -------
    dict
        report_type, as_of, period_days, trades_considered, trades_rejected, trades_ready,
        capital_protected_estimate, top_blocking_reasons, summary.
    """
    trades_considered = 0
    trades_rejected = 0
    trades_ready = 0
    capital_protected_estimate = 0.0
    reason_counts: Counter = Counter()

    for rec in history:
        if not isinstance(rec, dict):
            continue
        trades_considered += int(rec.get("trades_considered", 0))
        trades_rejected += int(rec.get("trades_rejected", 0))
        trades_ready += int(rec.get("trades_ready", 0))
        cap = rec.get("capital_protected_estimate")
        if cap is not None:
            try:
                capital_protected_estimate += float(cap)
            except (TypeError, ValueError):
                pass
        for item in rec.get("top_blocking_reasons") or []:
            if isinstance(item, dict):
                reason_counts[item.get("code") or "UNKNOWN"] += int(item.get("count", 0))
        by_reason = rec.get("by_reason") or {}
        for code, count in by_reason.items():
            reason_counts[code] += int(count)

    sorted_reasons = reason_counts.most_common(5)
    top_blocking_reasons = [{"code": code, "count": count} for code, count in sorted_reasons]

    summary = (
        f"Weekly: {trades_considered} considered, {trades_rejected} rejected, {trades_ready} READY. "
        f"Capital protected estimate: ${capital_protected_estimate:,.2f}."
    )

    return {
        "report_type": "weekly",
        "as_of": as_of or "",
        "period_days": len(history),
        "trades_considered": trades_considered,
        "trades_rejected": trades_rejected,
        "trades_ready": trades_ready,
        "capital_protected_estimate": round(capital_protected_estimate, 2),
        "top_blocking_reasons": top_blocking_reasons,
        "summary": summary,
    }


def report_to_markdown(report: Dict[str, Any]) -> str:
    """Export a daily or weekly trust report to Markdown (Phase 5.3 optional)."""
    lines = []
    rtype = report.get("report_type", "daily")
    lines.append(f"# Trust Report ({rtype.title()})")
    lines.append("")
    if report.get("as_of"):
        lines.append(f"**As of:** {report['as_of']}")
        lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(report.get("summary", "—"))
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append(f"- **Trades considered:** {report.get('trades_considered', 0)}")
    lines.append(f"- **Trades rejected:** {report.get('trades_rejected', 0)}")
    lines.append(f"- **Trades READY:** {report.get('trades_ready', 0)}")
    cap = report.get("capital_protected_estimate", 0)
    lines.append(f"- **Capital protected estimate:** ${cap:,.2f}")
    if report.get("capital_deployed_today") is not None:
        lines.append(f"- **Capital deployed today:** ${report['capital_deployed_today']:,.2f}")
    if report.get("month_to_date_realized_pnl") is not None:
        lines.append(f"- **Month-to-date realized PnL:** ${report['month_to_date_realized_pnl']:,.2f}")
    lines.append("")
    lines.append("## Top blocking reasons")
    lines.append("")
    for item in report.get("top_blocking_reasons") or []:
        code = item.get("code", "UNKNOWN")
        count = item.get("count", 0)
        lines.append(f"- {code}: {count}")
    if report.get("run_mode") is not None or report.get("config_frozen") is not None:
        lines.append("")
        lines.append("## Run & freeze (Phase 6.1)")
        lines.append("")
        if report.get("run_mode") is not None:
            lines.append(f"- **Run mode:** {report['run_mode']}")
        if report.get("config_frozen") is not None:
            lines.append(f"- **Config frozen:** {'YES' if report['config_frozen'] else 'NO'}")
        if report.get("freeze_violation_changed_keys"):
            lines.append(f"- **Changed keys (freeze violated):** {', '.join(report['freeze_violation_changed_keys'])}")
    lines.append("")
    return "\n".join(lines)
