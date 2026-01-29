"""Operator Action Recommendations (Phase 8.1).

Read-only advisory layer that derives clear, human-actionable recommendations
from existing diagnostics. No logic mutation, no persistence, no execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.ui.sandbox import SandboxResult
from app.ui.viability_analysis import SymbolViability, analyze_signal_viability


class RecommendationSeverity:
    """Severity levels for operator recommendations (Phase 8.1)."""
    
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class OperatorRecommendation:
    """A single operator action recommendation (Phase 8.1)."""

    severity: str  # HIGH, MEDIUM, or LOW
    title: str
    action: str  # Human-actionable recommendation
    evidence: List[str]  # Supporting evidence lines
    category: str  # e.g., "DATA_AVAILABILITY", "CONFIG_TUNING", "COVERAGE"


def _recommend_data_availability(
    snapshot: Dict[str, Any],
    viability_list: List[SymbolViability],
) -> List[OperatorRecommendation]:
    """Generate recommendations for data availability issues (Phase 8.1)."""
    recommendations: List[OperatorRecommendation] = []
    
    # Check exclusion summary for specific errors (primary check)
    exclusion_summary = snapshot.get("exclusion_summary")
    chain_fetch_errors = 0
    no_expirations = 0
    
    if isinstance(exclusion_summary, dict):
        rule_counts = exclusion_summary.get("rule_counts", {})
        chain_fetch_errors = rule_counts.get("CHAIN_FETCH_ERROR", 0)
        no_expirations = rule_counts.get("NO_EXPIRATIONS", 0)
    
    # Count symbols with data issues from viability analysis
    data_unavailable_count = sum(
        1 for v in viability_list if v.primary_blockage == "DATA_UNAVAILABLE"
    )
    
    # Also count from exclusion summary if viability analysis didn't catch it
    if data_unavailable_count == 0 and (chain_fetch_errors > 0 or no_expirations > 0):
        # Estimate affected symbols from exclusion summary
        if isinstance(exclusion_summary, dict):
            symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
            affected_symbols = set()
            if chain_fetch_errors > 0:
                affected_symbols.update(symbols_by_rule.get("CHAIN_FETCH_ERROR", []))
            if no_expirations > 0:
                affected_symbols.update(symbols_by_rule.get("NO_EXPIRATIONS", []))
            data_unavailable_count = len(affected_symbols) if affected_symbols else max(chain_fetch_errors, no_expirations)
    
    if data_unavailable_count > 0 or chain_fetch_errors > 0 or no_expirations > 0:
        evidence = []
        
        if data_unavailable_count > 0:
            evidence.append(f"{data_unavailable_count} symbol(s) failed due to data availability issues")
        
        if chain_fetch_errors > 0:
            evidence.append(f"{chain_fetch_errors} chain fetch error(s) detected")
        
        if no_expirations > 0:
            evidence.append(f"{no_expirations} symbol(s) have no available expirations")
        
        if evidence:
            recommendations.append(
                OperatorRecommendation(
                    severity=RecommendationSeverity.HIGH,
                    title="Data Availability Issues",
                    action=f"Investigate data provider connectivity for {data_unavailable_count if data_unavailable_count > 0 else max(chain_fetch_errors, no_expirations)} symbol(s). Check API keys, rate limits, and network connectivity.",
                    evidence=evidence,
                    category="DATA_AVAILABILITY",
                )
            )
    
    return recommendations


def _recommend_near_misses(
    snapshot: Dict[str, Any],
) -> List[OperatorRecommendation]:
    """Generate recommendations based on near-miss candidates (Phase 8.1)."""
    recommendations: List[OperatorRecommendation] = []
    
    near_misses = snapshot.get("near_misses") or []
    if not isinstance(near_misses, list) or len(near_misses) == 0:
        return recommendations
    
    # Group by failed rule
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for nm in near_misses:
        if isinstance(nm, dict):
            failed_rule = nm.get("failed_rule", "UNKNOWN")
            if failed_rule not in by_rule:
                by_rule[failed_rule] = []
            by_rule[failed_rule].append(nm)
    
    # Check for min_score near-misses (easy to fix)
    min_score_misses = by_rule.get("min_score", [])
    if len(min_score_misses) > 0:
        # Find the highest-scored near-miss
        highest_score = 0.0
        best_candidate = None
        for nm in min_score_misses:
            score = nm.get("actual_value")
            if isinstance(score, (int, float)) and score > highest_score:
                highest_score = score
                best_candidate = nm
        
        if best_candidate:
            required = best_candidate.get("required_value", 0.0)
            evidence = [
                f"{len(min_score_misses)} candidate(s) failed min_score threshold",
                f"Highest near-miss score: {highest_score:.4f} (required: {required:.4f})",
                f"Symbol: {best_candidate.get('symbol', 'N/A')}",
            ]
            
            recommendations.append(
                OperatorRecommendation(
                    severity=RecommendationSeverity.MEDIUM,
                    title="Near-Miss: min_score Threshold",
                    action=f"Consider lowering min_score from {required:.4f} to {highest_score:.4f} to capture {len(min_score_misses)} additional candidate(s).",
                    evidence=evidence,
                    category="CONFIG_TUNING",
                )
            )
    
    # Check for max_per_symbol near-misses
    max_per_symbol_misses = by_rule.get("max_per_symbol", [])
    if len(max_per_symbol_misses) > 0:
        symbols_affected = set(nm.get("symbol") for nm in max_per_symbol_misses if nm.get("symbol"))
        evidence = [
            f"{len(max_per_symbol_misses)} candidate(s) failed max_per_symbol cap",
            f"Affected symbols: {', '.join(sorted(symbols_affected)[:5])}" + (f" (+{len(symbols_affected) - 5} more)" if len(symbols_affected) > 5 else ""),
        ]
        
        recommendations.append(
            OperatorRecommendation(
                severity=RecommendationSeverity.LOW,
                title="Near-Miss: max_per_symbol Cap",
                action=f"Consider increasing max_per_symbol to allow more candidates from {len(symbols_affected)} symbol(s).",
                evidence=evidence,
                category="CONFIG_TUNING",
            )
        )
    
    return recommendations


def _recommend_coverage_issues(
    snapshot: Dict[str, Any],
) -> List[OperatorRecommendation]:
    """Generate recommendations based on coverage funnel analysis (Phase 8.1)."""
    recommendations: List[OperatorRecommendation] = []
    
    coverage_summary = snapshot.get("coverage_summary")
    if not isinstance(coverage_summary, dict):
        return recommendations
    
    by_symbol = coverage_summary.get("by_symbol", {})
    if not isinstance(by_symbol, dict):
        return recommendations
    
    # Find symbols with high generation but low selection
    high_attrition_symbols: List[tuple[str, int, int]] = []
    for symbol, counts in by_symbol.items():
        if isinstance(counts, dict):
            generation = counts.get("generation", 0)
            selection = counts.get("selection", 0)
            if generation > 5 and selection == 0:
                high_attrition_symbols.append((symbol, generation, selection))
    
    if high_attrition_symbols:
        # Sort by generation count (descending)
        high_attrition_symbols.sort(key=lambda x: x[1], reverse=True)
        
        top_symbols = high_attrition_symbols[:5]
        evidence = [
            f"{len(high_attrition_symbols)} symbol(s) generated candidates but none were selected",
        ]
        
        for symbol, gen_count, sel_count in top_symbols:
            evidence.append(f"{symbol}: {gen_count} generated, {sel_count} selected")
        
        recommendations.append(
            OperatorRecommendation(
                severity=RecommendationSeverity.MEDIUM,
                title="High Candidate Attrition",
                action=f"Review scoring weights or selection criteria for {len(high_attrition_symbols)} symbol(s) with high generation but zero selection.",
                evidence=evidence,
                category="COVERAGE",
            )
        )
    
    return recommendations


def _recommend_sandbox_insights(
    sandbox_result: Optional[SandboxResult],
) -> List[OperatorRecommendation]:
    """Generate recommendations based on sandbox analysis (Phase 8.1)."""
    recommendations: List[OperatorRecommendation] = []
    
    if not sandbox_result or not sandbox_result.newly_admitted:
        return recommendations
    
    # Check for min_score rejections
    min_score_rejections = []
    for nm in sandbox_result.newly_admitted:
        if isinstance(nm, dict):
            # Try to find rejection reason for this candidate
            reason = None
            
            # First, try exact key match
            key = _candidate_key(nm)
            if key:
                reason = sandbox_result.rejected_reasons.get(str(key))
            
            # If no exact match, check all reasons for min_score pattern
            # This handles cases where the key format might differ slightly
            if not reason or "min_score" not in str(reason).lower():
                for k, v in sandbox_result.rejected_reasons.items():
                    if isinstance(v, str) and "min_score" in v.lower():
                        # Check if this reason might apply to this candidate
                        # by checking symbol match
                        scored = nm.get("scored", {})
                        candidate = scored.get("candidate", {}) if isinstance(scored, dict) else {}
                        symbol = candidate.get("symbol") if isinstance(candidate, dict) else None
                        if symbol and symbol in str(k):
                            reason = v
                            break
                        # If no symbol match, use first min_score reason as fallback
                        if not reason:
                            reason = v
            
            if reason and "min_score" in str(reason).lower():
                min_score_rejections.append(nm)
    
    if len(min_score_rejections) > 0:
        evidence = [
            f"{len(min_score_rejections)} candidate(s) would be selected with sandbox parameters",
            "These candidates were rejected due to min_score threshold in live config",
        ]
        
        recommendations.append(
            OperatorRecommendation(
                severity=RecommendationSeverity.MEDIUM,
                title="Sandbox: Score Threshold Impact",
                action=f"Sandbox analysis shows {len(min_score_rejections)} candidate(s) would be viable with lower min_score. Consider calibration.",
                evidence=evidence,
                category="CONFIG_TUNING",
            )
        )
    
    return recommendations


def _candidate_key(candidate_dict: Dict[str, Any]) -> tuple:
    """Extract candidate key for comparison (Phase 8.1)."""
    if not isinstance(candidate_dict, dict):
        return None
    
    scored = candidate_dict.get("scored", {})
    if not isinstance(scored, dict):
        return None
    
    candidate = scored.get("candidate", {})
    if not isinstance(candidate, dict):
        return None
    
    return (
        candidate.get("symbol"),
        candidate.get("signal_type"),
        candidate.get("expiry"),
        candidate.get("strike"),
    )


def generate_operator_recommendations(
    snapshot: Dict[str, Any],
    sandbox_result: Optional[SandboxResult] = None,
) -> List[OperatorRecommendation]:
    """Generate operator action recommendations from diagnostics (Phase 8.1).
    
    This function:
    - Analyzes exclusion_summary, coverage_summary, near_misses, viability_analysis
    - Optionally incorporates sandbox_result insights
    - Generates ranked recommendations with severity and evidence
    
    Args:
        snapshot: DecisionSnapshot dict (from JSON)
        sandbox_result: Optional SandboxResult from sandbox evaluation
        
    Returns:
        List of OperatorRecommendation objects, sorted by severity (HIGH -> MEDIUM -> LOW)
        
    Note:
        This is read-only and does NOT modify the snapshot or any artifacts.
    """
    recommendations: List[OperatorRecommendation] = []
    
    # Analyze viability
    try:
        viability_list = analyze_signal_viability(snapshot)
    except Exception:
        viability_list = []
    
    # Generate recommendations from different sources
    recommendations.extend(_recommend_data_availability(snapshot, viability_list))
    recommendations.extend(_recommend_near_misses(snapshot))
    recommendations.extend(_recommend_coverage_issues(snapshot))
    
    if sandbox_result:
        recommendations.extend(_recommend_sandbox_insights(sandbox_result))
    
    # Sort by severity (HIGH -> MEDIUM -> LOW)
    severity_order = {
        RecommendationSeverity.HIGH: 0,
        RecommendationSeverity.MEDIUM: 1,
        RecommendationSeverity.LOW: 2,
    }
    
    recommendations.sort(key=lambda r: severity_order.get(r.severity, 99))
    
    return recommendations


__all__ = [
    "OperatorRecommendation",
    "RecommendationSeverity",
    "generate_operator_recommendations",
]
