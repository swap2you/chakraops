from __future__ import annotations

"""Decision snapshot JSON contract (Phase 4B Step 2).

This module creates a JSON-serializable snapshot of a SignalRunResult.
It does NOT modify generation, scoring, selection, or explainability behavior.

The snapshot is a pure data structure that preserves all information
from the engine run in a deterministic, serializable format.

Phase 3: Candidates include option_context (expected move, IV rank, term structure,
skew, days to earnings, event flags) when available. Exclusions include context
gating rules (iv_rank_low_sell, iv_rank_high_sell, expected_move_exceeds_strike_distance,
event_within_window) with stage SELECTION.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List

from app.signals.models import ExclusionDetail, ExclusionReason

if TYPE_CHECKING:
    from app.signals.engine import SignalRunResult


@dataclass(frozen=True)
class DecisionSnapshot:
    """JSON-serializable snapshot of a signal engine run decision.

    All fields are deterministic and can be serialized to JSON without
    custom encoders. Datetimes are ISO strings, dataclasses are dicts.
    """

    as_of: str  # ISO datetime string
    universe_id_or_hash: str
    stats: Dict[str, int]
    candidates: List[Dict[str, Any]]
    scored_candidates: List[Dict[str, Any]] | None
    selected_signals: List[Dict[str, Any]] | None
    explanations: List[Dict[str, Any]] | None
    exclusions: List[Dict[str, Any]] | None = None  # Phase 7.2: Detailed exclusion information
    exclusion_summary: Dict[str, Any] | None = None  # Phase 7.3: Aggregated exclusion diagnostics
    coverage_summary: Dict[str, Any] | None = None  # Phase 7.4: Coverage funnel per symbol
    near_misses: List[Dict[str, Any]] | None = None  # Phase 7.4: Candidates that failed exactly one rule
    # Phase 8: Partial-universe options availability
    symbols_with_options: List[str] | None = None  # Symbols that had valid options data
    symbols_without_options: Dict[str, str] | None = None  # symbol -> reason (NO_EXPIRATIONS, EMPTY_CHAIN, etc.)


def _convert_datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string for JSON serialization."""
    return dt.isoformat()


def _convert_to_json_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types.
    
    Handles:
    - datetime -> ISO string
    - date -> ISO string
    - dataclasses -> dicts
    - lists -> lists with converted elements
    - dicts -> dicts with converted values
    - enums -> their values (handled by asdict)
    """
    if obj is None:
        return None
    
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    if isinstance(obj, date):
        return obj.isoformat()
    
    # Check if it's a dataclass (but not a dict or list)
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _convert_to_json_serializable(v) for k, v in asdict(obj).items()}
    
    if isinstance(obj, list):
        return [_convert_to_json_serializable(item) for item in obj]
    
    if isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    
    # Primitive types (str, int, float, bool) pass through
    return obj


def _convert_list_of_dataclasses(lst: List[Any] | None) -> List[Dict[str, Any]] | None:
    """Convert a list of dataclasses to a list of dicts with JSON-serializable values."""
    if lst is None:
        return None
    return [_convert_to_json_serializable(item) for item in lst]


def _determine_exclusion_stage(exclusion: ExclusionReason) -> str:
    """Determine exclusion stage from exclusion code and data (Phase 7.2).
    
    Maps exclusion codes to stages for better organization in UI.
    """
    code = exclusion.code.upper()
    
    # Chain fetch stage
    if code in ("CHAIN_FETCH_ERROR", "NO_EXPIRATIONS"):
        return "CHAIN_FETCH"
    
    # Normalization stage (from adapter)
    if code in ("NO_OPTIONS_FOR_SYMBOL", "INVALID_EXPIRY", "INVALID_STRIKE", "MISSING_REQUIRED_FIELD"):
        return "NORMALIZATION"
    
    # CSP generation stage
    if code in ("NO_OPTIONS_FOR_SYMBOL", "NO_EXPIRY_IN_DTE_WINDOW", "NO_LIQUID_PUTS", 
                "NO_STRIKES_IN_OTM_RANGE", "NO_STRIKES_IN_DELTA_RANGE", "NO_UNDERLYING_PRICE"):
        # Check if it's CSP-specific by checking data or message
        if "PUT" in exclusion.message.upper() or exclusion.data.get("signal_type") == "CSP":
            return "CSP_GENERATION"
    
    # CC generation stage
    if code in ("NO_OPTIONS_FOR_SYMBOL", "NO_EXPIRY_IN_DTE_WINDOW", "NO_LIQUID_CALLS",
                "NO_STRIKES_IN_OTM_RANGE", "NO_STRIKES_IN_DELTA_RANGE", "NO_UNDERLYING_PRICE"):
        # Check if it's CC-specific
        if "CALL" in exclusion.message.upper() or exclusion.data.get("signal_type") == "CC":
            return "CC_GENERATION"

    # Phase 2.4: confidence gating (after scoring, before execution)
    if code == "CONFIDENCE_BELOW_THRESHOLD":
        return "SELECTION"

    # Phase 3.2: options context gating (IV rank, expected move, event window)
    if code in (
        "IV_RANK_LOW_SELL",
        "IV_RANK_HIGH_SELL",
        "IV_RANK_HIGH_BUY",
        "EXPECTED_MOVE_EXCEEDS_STRIKE_DISTANCE",
        "EVENT_WITHIN_WINDOW",
    ):
        return "SELECTION"

    # Phase 2.5: portfolio caps (execution guard)
    if code in ("MAX_POSITIONS", "RISK_BUDGET", "SECTOR_CAP", "DELTA_EXPOSURE"):
        return "PORTFOLIO"

    # Default fallback
    return "UNKNOWN"


def _convert_exclusions_to_details(exclusions: List[ExclusionReason]) -> List[ExclusionDetail]:
    """Convert ExclusionReason objects to ExclusionDetail objects (Phase 7.2).
    
    Extracts symbol from exclusion data and determines stage from code/message.
    """
    details: List[ExclusionDetail] = []
    
    for excl in exclusions:
        # Extract symbol from data, fallback to "UNKNOWN"
        symbol = excl.data.get("symbol", "UNKNOWN") if isinstance(excl.data, dict) else "UNKNOWN"
        if not symbol or symbol == "":
            symbol = "UNKNOWN"
        
        # Determine stage
        stage = _determine_exclusion_stage(excl)
        
        # Create ExclusionDetail
        detail = ExclusionDetail(
            symbol=str(symbol),
            rule=excl.code,
            message=excl.message,
            stage=stage,
            metadata=excl.data if excl.data else None,
        )
        details.append(detail)
    
    return details


def _build_exclusion_summary(exclusion_details: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """Build exclusion summary diagnostics from exclusion details (Phase 7.3).
    
    Aggregates:
    - Counts by rule
    - Counts by stage
    - Symbols impacted per rule
    
    Returns None if exclusion_details is empty or None.
    """
    if not exclusion_details or len(exclusion_details) == 0:
        return None
    
    # Counts by rule
    rule_counts: Dict[str, int] = {}
    # Counts by stage
    stage_counts: Dict[str, int] = {}
    # Symbols per rule
    symbols_by_rule: Dict[str, List[str]] = {}
    
    for excl in exclusion_details:
        if not isinstance(excl, dict):
            continue
        
        rule = excl.get("rule", "UNKNOWN")
        stage = excl.get("stage", "UNKNOWN")
        symbol = excl.get("symbol", "UNKNOWN")
        
        # Count by rule
        rule_counts[rule] = rule_counts.get(rule, 0) + 1
        
        # Count by stage
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        
        # Symbols per rule (deduplicated)
        if rule not in symbols_by_rule:
            symbols_by_rule[rule] = []
        if symbol not in symbols_by_rule[rule] and symbol != "UNKNOWN":
            symbols_by_rule[rule].append(symbol)
    
    # Sort symbols deterministically
    for rule in symbols_by_rule:
        symbols_by_rule[rule].sort()
    
    return {
        "rule_counts": rule_counts,
        "stage_counts": stage_counts,
        "symbols_by_rule": symbols_by_rule,
    }


def _build_coverage_summary(
    result: "SignalRunResult",
    candidates_dicts: List[Dict[str, Any]] | None,
    scored_candidates_dicts: List[Dict[str, Any]] | None,
    selected_signals_dicts: List[Dict[str, Any]] | None,
) -> Dict[str, Any] | None:
    """Build coverage summary per symbol (Phase 7.4).
    
    Tracks funnel counts at each stage:
    - normalization: Symbols that attempted normalization (inferred from stats)
    - generation: Candidates generated per symbol
    - scoring: Candidates scored per symbol
    - selection: Signals selected per symbol
    
    Returns None if insufficient data.
    """
    if not candidates_dicts:
        return None
    
    # Get symbols evaluated from stats
    symbols_evaluated = result.stats.get("symbols_evaluated", 0)
    if symbols_evaluated == 0:
        return None
    
    # Count candidates per symbol (generation stage)
    generation_by_symbol: Dict[str, int] = {}
    for cand in candidates_dicts:
        if isinstance(cand, dict):
            symbol = cand.get("symbol", "UNKNOWN")
            if symbol != "UNKNOWN":
                generation_by_symbol[symbol] = generation_by_symbol.get(symbol, 0) + 1
    
    # Count scored candidates per symbol (scoring stage)
    scoring_by_symbol: Dict[str, int] = {}
    if scored_candidates_dicts:
        for scored in scored_candidates_dicts:
            if isinstance(scored, dict):
                candidate = scored.get("candidate", {})
                if isinstance(candidate, dict):
                    symbol = candidate.get("symbol", "UNKNOWN")
                    if symbol != "UNKNOWN":
                        scoring_by_symbol[symbol] = scoring_by_symbol.get(symbol, 0) + 1
    
    # Count selected signals per symbol (selection stage)
    selection_by_symbol: Dict[str, int] = {}
    if selected_signals_dicts:
        for selected in selected_signals_dicts:
            if isinstance(selected, dict):
                scored = selected.get("scored", {})
                if isinstance(scored, dict):
                    candidate = scored.get("candidate", {})
                    if isinstance(candidate, dict):
                        symbol = candidate.get("symbol", "UNKNOWN")
                        if symbol != "UNKNOWN":
                            selection_by_symbol[symbol] = selection_by_symbol.get(symbol, 0) + 1
    
    # Build per-symbol coverage
    all_symbols = set(generation_by_symbol.keys())
    if scored_candidates_dicts:
        for scored in scored_candidates_dicts:
            if isinstance(scored, dict):
                candidate = scored.get("candidate", {})
                if isinstance(candidate, dict):
                    symbol = candidate.get("symbol", "UNKNOWN")
                    if symbol != "UNKNOWN":
                        all_symbols.add(symbol)
    
    coverage_by_symbol: Dict[str, Dict[str, int]] = {}
    for symbol in sorted(all_symbols):
        coverage_by_symbol[symbol] = {
            "normalization": 1 if symbol in generation_by_symbol or symbol in scoring_by_symbol else 0,  # Attempted
            "generation": generation_by_symbol.get(symbol, 0),
            "scoring": scoring_by_symbol.get(symbol, 0),
            "selection": selection_by_symbol.get(symbol, 0),
        }
    
    return {
        "by_symbol": coverage_by_symbol,
        "total_symbols_evaluated": symbols_evaluated,
    }


def _identify_near_misses(
    scored_candidates_dicts: List[Dict[str, Any]] | None,
    selected_signals_dicts: List[Dict[str, Any]] | None,
    selection_config: Dict[str, Any] | None,
    max_near_misses: int = 10,
) -> List[Dict[str, Any]] | None:
    """Identify near-miss candidates that failed exactly one rule (Phase 7.4).
    
    A near-miss is a scored candidate that:
    - Was scored but not selected
    - Failed exactly one selection rule
    
    Rules checked:
    - min_score threshold
    - max_per_symbol cap
    - max_per_signal_type cap
    - max_total cap
    
    Returns top N near-misses sorted by score (descending).
    """
    if not scored_candidates_dicts or not selection_config:
        return None
    
    # Build set of selected candidate keys (symbol, signal_type, expiry, strike)
    selected_keys = set()
    if selected_signals_dicts:
        for selected in selected_signals_dicts:
            if isinstance(selected, dict):
                scored = selected.get("scored", {})
                if isinstance(scored, dict):
                    candidate = scored.get("candidate", {})
                    if isinstance(candidate, dict):
                        key = (
                            candidate.get("symbol"),
                            candidate.get("signal_type"),
                            candidate.get("expiry"),
                            candidate.get("strike"),
                        )
                        if all(k is not None for k in key):
                            selected_keys.add(key)
    
    # Get selection config values
    min_score = selection_config.get("min_score")
    max_per_symbol = selection_config.get("max_per_symbol", 0)
    max_per_signal_type = selection_config.get("max_per_signal_type")
    max_total = selection_config.get("max_total", 0)
    
    # Count selected per symbol and signal type
    selected_by_symbol: Dict[str, int] = {}
    selected_by_type: Dict[str, int] = {}
    if selected_signals_dicts:
        for selected in selected_signals_dicts:
            if isinstance(selected, dict):
                scored = selected.get("scored", {})
                if isinstance(scored, dict):
                    candidate = scored.get("candidate", {})
                    if isinstance(candidate, dict):
                        symbol = candidate.get("symbol")
                        signal_type = candidate.get("signal_type")
                        if symbol:
                            selected_by_symbol[symbol] = selected_by_symbol.get(symbol, 0) + 1
                        if signal_type:
                            selected_by_type[signal_type] = selected_by_type.get(signal_type, 0) + 1
    
    selected_count = len(selected_signals_dicts) if selected_signals_dicts else 0
    
    # Identify near-misses
    near_misses: List[Dict[str, Any]] = []
    
    for scored_dict in scored_candidates_dicts:
        if not isinstance(scored_dict, dict):
            continue
        
        candidate = scored_dict.get("candidate", {})
        if not isinstance(candidate, dict):
            continue
        
        score_dict = scored_dict.get("score", {})
        if not isinstance(score_dict, dict):
            continue
        
        symbol = candidate.get("symbol")
        signal_type = candidate.get("signal_type")
        expiry = candidate.get("expiry")
        strike = candidate.get("strike")
        total_score = score_dict.get("total")
        
        # Skip if already selected
        key = (symbol, signal_type, expiry, strike)
        if all(k is not None for k in key) and key in selected_keys:
            continue
        
        # Determine which rule(s) failed
        failed_rules = []
        
        # Check min_score
        if min_score is not None and total_score is not None:
            if total_score < min_score:
                failed_rules.append("min_score")
        
        # Check max_per_symbol
        if symbol and max_per_symbol > 0:
            if selected_by_symbol.get(symbol, 0) >= max_per_symbol:
                failed_rules.append("max_per_symbol")
        
        # Check max_per_signal_type
        if signal_type and max_per_signal_type is not None:
            if selected_by_type.get(signal_type, 0) >= max_per_signal_type:
                failed_rules.append("max_per_signal_type")
        
        # Check max_total
        if max_total > 0 and selected_count >= max_total:
            failed_rules.append("max_total")
        
        # Only include if failed exactly one rule
        if len(failed_rules) == 1:
            failed_rule = failed_rules[0]
            
            # Determine actual_value and required_value
            actual_value = None
            required_value = None
            
            if failed_rule == "min_score":
                actual_value = total_score
                required_value = min_score
            elif failed_rule == "max_per_symbol":
                actual_value = selected_by_symbol.get(symbol, 0)
                required_value = max_per_symbol
            elif failed_rule == "max_per_signal_type":
                actual_value = selected_by_type.get(signal_type, 0)
                required_value = max_per_signal_type
            elif failed_rule == "max_total":
                actual_value = selected_count
                required_value = max_total
            
            near_misses.append({
                "symbol": symbol,
                "strategy": signal_type,  # CSP or CC
                "failed_rule": failed_rule,
                "actual_value": actual_value,
                "required_value": required_value,
                "stage": "selection",
                "score": total_score,
                "expiry": expiry,
                "strike": strike,
            })
    
    # Sort by score (descending) and limit to top N
    near_misses.sort(key=lambda x: x.get("score") or 0.0, reverse=True)
    return near_misses[:max_near_misses] if near_misses else None


def _derive_operator_verdict(exclusion_summary: Dict[str, Any] | None) -> str:
    """Derive operator verdict from exclusion summary (Phase 7.3).
    
    Returns a single-line diagnostic verdict explaining why the system is blocked.
    """
    if not exclusion_summary:
        return "No exclusion data available"
    
    rule_counts = exclusion_summary.get("rule_counts", {})
    if not rule_counts or len(rule_counts) == 0:
        return "No exclusion rules found"
    
    # Find top blocking rule
    sorted_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)
    if not sorted_rules:
        return "No blocking rules identified"
    
    top_rule, top_count = sorted_rules[0]
    symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
    affected_symbols = symbols_by_rule.get(top_rule, [])
    
    # Build verdict
    if len(affected_symbols) > 0:
        symbol_list = ", ".join(affected_symbols[:5])  # Limit to 5 symbols
        if len(affected_symbols) > 5:
            symbol_list += f" (+{len(affected_symbols) - 5} more)"
        return f"Blocked by {top_rule} ({top_count} occurrences) affecting {symbol_list}"
    else:
        return f"Blocked by {top_rule} ({top_count} occurrences)"


def build_decision_snapshot(
    result: "SignalRunResult",
    options_diagnostics: Dict[str, Any] | None = None,
) -> DecisionSnapshot:
    """Build a JSON-serializable snapshot from a SignalRunResult.

    Preserves all data and ordering from the result. Converts:
    - datetime -> ISO string
    - dataclasses -> dicts (via asdict)
    - enums -> their values (handled by asdict)

    Args:
        result: SignalRunResult from run_signal_engine
        options_diagnostics: Optional dict with symbols_with_options (list) and
            symbols_without_options (dict symbol -> reason) for partial-universe visibility.

    Returns:
        DecisionSnapshot with all fields converted to JSON-serializable types
    """
    # Convert datetime to ISO string
    as_of_iso = _convert_datetime_to_iso(result.as_of)

    # Convert lists of dataclasses to lists of dicts
    candidates_dicts = _convert_list_of_dataclasses(result.candidates)
    scored_candidates_dicts = _convert_list_of_dataclasses(result.scored_candidates)
    selected_signals_dicts = _convert_list_of_dataclasses(result.selected_signals)
    explanations_dicts = _convert_list_of_dataclasses(result.explanations)
    
    # Convert exclusions to ExclusionDetail objects, then to dicts (Phase 7.2)
    exclusions_details: List[Dict[str, Any]] | None = None
    exclusion_summary: Dict[str, Any] | None = None
    if result.exclusions and len(result.exclusions) > 0:
        exclusion_details_objects = _convert_exclusions_to_details(result.exclusions)
        exclusions_details = _convert_list_of_dataclasses(exclusion_details_objects)
        # Build exclusion summary from details (Phase 7.3)
        exclusion_summary = _build_exclusion_summary(exclusions_details)
    
    # Build coverage summary (Phase 7.4)
    coverage_summary = _build_coverage_summary(
        result=result,
        candidates_dicts=candidates_dicts,
        scored_candidates_dicts=scored_candidates_dicts,
        selected_signals_dicts=selected_signals_dicts,
    )
    
    # Identify near-misses (Phase 7.4)
    # Extract selection_config from explanations (policy_snapshot)
    selection_config = None
    if explanations_dicts and len(explanations_dicts) > 0:
        # Get policy_snapshot from first explanation
        first_expl = explanations_dicts[0]
        if isinstance(first_expl, dict):
            policy_snapshot = first_expl.get("policy_snapshot", {})
            if isinstance(policy_snapshot, dict) and len(policy_snapshot) > 0:
                selection_config = policy_snapshot
    
    near_misses = _identify_near_misses(
        scored_candidates_dicts=scored_candidates_dicts,
        selected_signals_dicts=selected_signals_dicts,
        selection_config=selection_config,
        max_near_misses=10,
    )

    # Phase 8: Partial-universe options availability
    symbols_with_options: List[str] | None = None
    symbols_without_options: Dict[str, str] | None = None
    if options_diagnostics:
        symbols_with_options = options_diagnostics.get("symbols_with_options")
        symbols_without_options = options_diagnostics.get("symbols_without_options")
        if symbols_with_options is not None and not isinstance(symbols_with_options, list):
            symbols_with_options = None
        if symbols_without_options is not None and not isinstance(symbols_without_options, dict):
            symbols_without_options = None

    return DecisionSnapshot(
        as_of=as_of_iso,
        universe_id_or_hash=result.universe_id_or_hash,
        stats=result.stats.copy(),  # Already a dict, just copy
        candidates=candidates_dicts or [],
        scored_candidates=scored_candidates_dicts,
        selected_signals=selected_signals_dicts,
        explanations=explanations_dicts,
        exclusions=exclusions_details,  # Phase 7.2
        exclusion_summary=exclusion_summary,  # Phase 7.3
        coverage_summary=coverage_summary,  # Phase 7.4
        near_misses=near_misses,  # Phase 7.4
        symbols_with_options=symbols_with_options,
        symbols_without_options=symbols_without_options,
    )


__all__ = ["DecisionSnapshot", "build_decision_snapshot", "_derive_operator_verdict"]
