"""Slack notification module for Phase 7 decision alerts (Phase 7.1).

This module sends read-only decision intelligence alerts to Slack.
It does NOT execute trades or call brokers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.execution.execution_gate import ExecutionGateResult
from app.execution.execution_plan import ExecutionPlan
from app.signals.decision_snapshot import DecisionSnapshot


def _format_signal_summary(selected_signals: List[Dict[str, Any]], max_signals: int = 3) -> List[str]:
    """Format top selected signals for Slack message."""
    if not selected_signals:
        return []
    
    lines: List[str] = []
    for i, selected in enumerate(selected_signals[:max_signals], 1):
        scored = selected.get("scored", {}) if isinstance(selected, dict) else {}
        candidate = scored.get("candidate", {}) if isinstance(scored, dict) else {}
        score = scored.get("score", {}) if isinstance(scored, dict) else {}
        
        symbol = candidate.get("symbol", "N/A")
        signal_type = candidate.get("signal_type", "N/A")
        strike = candidate.get("strike", "N/A")
        expiry = candidate.get("expiry", "N/A")
        limit_price = candidate.get("mid") or candidate.get("bid") or "N/A"
        total_score = score.get("total", "N/A")
        
        # Format limit price
        if isinstance(limit_price, (int, float)):
            limit_price_str = f"${limit_price:.2f}"
        else:
            limit_price_str = str(limit_price)
        
        # Format score
        if isinstance(total_score, (int, float)):
            score_str = f"{total_score:.4f}"
        else:
            score_str = str(total_score)
        
        lines.append(
            f"{i}. *{symbol}* {signal_type} | Strike: ${strike} | "
            f"Expiry: {expiry} | Price: {limit_price_str} | Score: {score_str}"
        )
    
    return lines


def send_decision_alert(
    snapshot: DecisionSnapshot,
    gate_result: ExecutionGateResult,
    execution_plan: ExecutionPlan,
    decision_file_path: Optional[Path] = None,
    webhook_url: Optional[str] = None,
) -> None:
    """Send Phase 7 decision alert to Slack.

    This function formats and sends a read-only decision intelligence alert.
    It does NOT execute trades or call brokers.

    Args:
        snapshot: DecisionSnapshot from signal engine
        gate_result: ExecutionGateResult from gate evaluation
        execution_plan: ExecutionPlan with orders (if allowed)
        decision_file_path: Optional path to decision JSON file (for reference)
        webhook_url: Optional Slack webhook URL (defaults to SLACK_WEBHOOK_URL env var)

    Raises:
        ValueError: If webhook URL is not provided and not found in environment.
        requests.RequestException: If HTTP request fails.

    Note:
        This function is designed to fail gracefully. If Slack is unavailable,
        the pipeline should continue (caller should catch exceptions).
    """
    if webhook_url is None:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        raise ValueError(
            "SLACK_WEBHOOK_URL is not set. "
            "Slack alerts are optional. Set SLACK_WEBHOOK_URL to enable alerts."
        )

    # Build message lines
    lines: List[str] = []
    
    # Header
    lines.append("*ChakraOps Phase 7 Decision Alert*")
    lines.append("")
    
    # Timestamp and universe
    lines.append(f"*Timestamp:* {snapshot.as_of}")
    lines.append(f"*Universe:* {snapshot.universe_id_or_hash}")
    lines.append("")
    
    # Gate status
    gate_status = "ALLOWED" if gate_result.allowed else "BLOCKED"
    status_emoji = "✅" if gate_result.allowed else "❌"
    lines.append(f"*Gate Status:* {status_emoji} {gate_status}")
    lines.append("")
    
    # If blocked, show reasons
    if not gate_result.allowed:
        if gate_result.reasons:
            lines.append("*Block Reasons:*")
            for reason in gate_result.reasons:
                lines.append(f"• {reason}")
        else:
            lines.append("*Block Reason:* (no reason provided)")
        lines.append("")
        
        # Phase 7.3: Include operator verdict and top blocking rule
        exclusion_summary = snapshot.exclusion_summary
        if isinstance(exclusion_summary, dict):
            # Operator verdict
            verdict = _derive_operator_verdict(exclusion_summary)
            lines.append(f"*Diagnostic Verdict:* {verdict}")
            lines.append("")
            
            # Top blocking rule
            rule_counts = exclusion_summary.get("rule_counts", {})
            if rule_counts:
                sorted_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)
                top_rule, top_count = sorted_rules[0]
                lines.append(f"*Top Blocking Rule:* {top_rule} ({top_count} occurrence(s))")
                lines.append("")
        
        # Phase 7.4: Coverage and near-miss summary (optional, concise)
        coverage_summary = snapshot.coverage_summary if snapshot.coverage_summary else None
        near_misses = snapshot.near_misses if snapshot.near_misses else None
        
        if isinstance(coverage_summary, dict) or (isinstance(near_misses, list) and len(near_misses) > 0):
            coverage_lines = []
            
            # Dominant attrition stage
            if isinstance(coverage_summary, dict):
                coverage_by_symbol = coverage_summary.get("by_symbol", {})
                if coverage_by_symbol:
                    # Find stage with most attrition (generation -> scoring -> selection)
                    total_generation = sum(c.get("generation", 0) for c in coverage_by_symbol.values())
                    total_scoring = sum(c.get("scoring", 0) for c in coverage_by_symbol.values())
                    total_selection = sum(c.get("selection", 0) for c in coverage_by_symbol.values())
                    
                    attrition_generation = total_generation - total_scoring
                    attrition_scoring = total_scoring - total_selection
                    
                    if attrition_generation > attrition_scoring and attrition_generation > 0:
                        coverage_lines.append(f"*Dominant Attrition:* Generation → Scoring ({attrition_generation} candidates lost)")
                    elif attrition_scoring > 0:
                        coverage_lines.append(f"*Dominant Attrition:* Scoring → Selection ({attrition_scoring} candidates lost)")
            
            # Near-miss count
            if isinstance(near_misses, list) and len(near_misses) > 0:
                coverage_lines.append(f"*Near-Misses:* {len(near_misses)} candidate(s) failed exactly one rule")
            
            if coverage_lines:
                lines.extend(coverage_lines)
                lines.append("")
        else:
            # Phase 7.2 fallback: Include top exclusion rules summary if available
            snapshot_exclusions = snapshot.exclusions or []
            if isinstance(snapshot_exclusions, list) and len(snapshot_exclusions) > 0:
                # Count exclusions by rule
                rule_counts: Dict[str, int] = {}
                for excl in snapshot_exclusions:
                    if isinstance(excl, dict):
                        rule = excl.get("rule", "UNKNOWN")
                        rule_counts[rule] = rule_counts.get(rule, 0) + 1
                
                # Show top 3 rules by count
                if rule_counts:
                    sorted_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                    lines.append("*Top Exclusion Rules:*")
                    for rule, count in sorted_rules:
                        lines.append(f"• {rule}: {count} occurrence(s)")
                    lines.append("")
    
    # If allowed, show top signals
    if gate_result.allowed:
        selected_signals = snapshot.selected_signals or []
        if selected_signals:
            lines.append(f"*Top Selected Signals ({min(len(selected_signals), 3)} of {len(selected_signals)}):*")
            signal_lines = _format_signal_summary(selected_signals, max_signals=3)
            lines.extend(signal_lines)
            lines.append("")
            
            # Show execution plan summary
            if execution_plan.orders:
                lines.append(f"*Execution Plan:* {len(execution_plan.orders)} order(s)")
                lines.append("")
        else:
            lines.append("*Selected Signals:* None")
            lines.append("")
    
    # Decision file path (if provided)
    if decision_file_path:
        lines.append(f"*Decision File:* `{decision_file_path.name}`")
        lines.append("")
    
    # Footer note
    lines.append("_⚠️ Manual execution only. No trades are auto-executed._")
    
    # Join message
    message = "\n".join(lines)
    
    # Prepare JSON payload
    payload = {"text": message}
    
    # Send to Slack
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ValueError(
            f"Slack webhook returned error {response.status_code}: {response.text}"
        ) from exc
    except requests.RequestException as exc:
        raise ValueError(f"Failed to send Slack message: {exc}") from exc


__all__ = ["send_decision_alert"]
