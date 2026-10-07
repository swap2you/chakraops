"""Operator Calibration Sandbox (Phase 7.5).

Read-only sandbox for hypothetical selection recalculation.
Does NOT modify live artifacts, alerts, or execution logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.signals.models import SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore, ScoreComponent
from app.signals.selection import SelectionConfig, SelectedSignal, select_signals
from app.signals.models import SignalCandidate
from datetime import datetime, date


@dataclass(frozen=True)
class SandboxParams:
    """Sandbox selection parameters (Phase 7.5)."""

    min_score: float | None
    max_total: int
    max_per_symbol: int
    max_per_signal_type: int | None


@dataclass(frozen=True)
class SandboxResult:
    """Result of sandbox selection evaluation (Phase 7.5)."""

    selected_count: int
    selected_signals: List[Dict[str, Any]]
    newly_admitted: List[Dict[str, Any]]  # Candidates in sandbox but not in live
    rejected_reasons: Dict[str, str]  # Why each newly_admitted candidate failed live


def _reconstruct_scored_candidate(scored_dict: Dict[str, Any]) -> Optional[ScoredSignalCandidate]:
    """Reconstruct ScoredSignalCandidate from dict (Phase 7.5).
    
    This is a read-only reconstruction for sandbox evaluation.
    """
    if not isinstance(scored_dict, dict):
        return None
    
    candidate_dict = scored_dict.get("candidate", {})
    score_dict = scored_dict.get("score", {})
    rank = scored_dict.get("rank")
    
    if not isinstance(candidate_dict, dict) or not isinstance(score_dict, dict):
        return None
    
    # Reconstruct SignalCandidate
    try:
        symbol = candidate_dict.get("symbol")
        signal_type_str = candidate_dict.get("signal_type")
        if isinstance(signal_type_str, dict):
            signal_type_str = signal_type_str.get("value") or signal_type_str.get("name")
        signal_type = SignalType(signal_type_str) if signal_type_str else None
        
        as_of_str = candidate_dict.get("as_of")
        as_of = datetime.fromisoformat(as_of_str) if isinstance(as_of_str, str) else datetime.now()
        
        expiry_str = candidate_dict.get("expiry")
        expiry = date.fromisoformat(expiry_str) if isinstance(expiry_str, str) else None
        
        if not symbol or not signal_type or not expiry:
            return None
        
        candidate = SignalCandidate(
            symbol=symbol,
            signal_type=signal_type,
            as_of=as_of,
            underlying_price=candidate_dict.get("underlying_price", 0.0),
            expiry=expiry,
            strike=candidate_dict.get("strike", 0.0),
            option_right=candidate_dict.get("option_right", "PUT"),
            bid=candidate_dict.get("bid"),
            ask=candidate_dict.get("ask"),
            mid=candidate_dict.get("mid"),
            volume=candidate_dict.get("volume"),
            open_interest=candidate_dict.get("open_interest"),
            delta=candidate_dict.get("delta"),
            prob_otm=candidate_dict.get("prob_otm"),
            iv_rank=candidate_dict.get("iv_rank"),
            iv=candidate_dict.get("iv"),
            annualized_yield=candidate_dict.get("annualized_yield"),
            raw_yield=candidate_dict.get("raw_yield"),
            max_profit=candidate_dict.get("max_profit"),
            collateral=candidate_dict.get("collateral"),
        )
    except (ValueError, TypeError, KeyError) as e:
        # If reconstruction fails, skip this candidate
        return None
    
    # Reconstruct SignalScore
    try:
        total = score_dict.get("total", 0.0)
        components_dicts = score_dict.get("components", [])
        components = []
        for comp_dict in components_dicts:
            if isinstance(comp_dict, dict):
                components.append(
                    ScoreComponent(
                        name=comp_dict.get("name", ""),
                        value=comp_dict.get("value", 0.0),
                        weight=comp_dict.get("weight", 1.0),
                    )
                )
        
        score = SignalScore(total=total, components=components)
    except (ValueError, TypeError, KeyError):
        return None
    
    return ScoredSignalCandidate(candidate=candidate, score=score, rank=rank)


def _candidate_key(candidate_dict: Dict[str, Any]) -> tuple:
    """Extract candidate key for comparison."""
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


def _determine_rejection_reason(
    candidate: ScoredSignalCandidate,
    live_selected_keys: set,
    live_config: Dict[str, Any],
    live_selected_dicts: List[Dict[str, Any]],
) -> str:
    """Determine why a candidate was rejected in live selection (Phase 7.5).
    
    This re-runs the live selection logic to determine the exact reason.
    """
    key = (candidate.candidate.symbol, candidate.candidate.signal_type.value, 
           candidate.candidate.expiry.isoformat() if isinstance(candidate.candidate.expiry, date) else str(candidate.candidate.expiry),
           candidate.candidate.strike)
    
    # Check if already selected
    if key in live_selected_keys:
        return "ALREADY_SELECTED"
    
    # Extract live config
    live_min_score = live_config.get("min_score")
    live_max_total = live_config.get("max_total", 10)
    live_max_per_symbol = live_config.get("max_per_symbol", 2)
    live_max_per_signal_type = live_config.get("max_per_signal_type")
    
    # Check min_score
    if live_min_score is not None and candidate.score.total < live_min_score:
        return f"min_score: {candidate.score.total:.4f} < {live_min_score:.4f}"
    
    # Count live selections per symbol and per type
    symbol_count = sum(1 for ld in live_selected_dicts 
                      if isinstance(ld, dict) and 
                      ld.get("scored", {}).get("candidate", {}).get("symbol") == candidate.candidate.symbol)
    
    type_count = sum(1 for ld in live_selected_dicts 
                    if isinstance(ld, dict) and 
                    ld.get("scored", {}).get("candidate", {}).get("signal_type") == candidate.candidate.signal_type.value)
    
    # Check max_per_symbol
    if symbol_count >= live_max_per_symbol:
        return f"max_per_symbol: {symbol_count} >= {live_max_per_symbol} (for {candidate.candidate.symbol})"
    
    # Check max_per_signal_type
    if live_max_per_signal_type is not None and type_count >= live_max_per_signal_type:
        return f"max_per_signal_type: {type_count} >= {live_max_per_signal_type} (for {candidate.candidate.signal_type.value})"
    
    # Check max_total
    if len(live_selected_dicts) >= live_max_total:
        return f"max_total: {len(live_selected_dicts)} >= {live_max_total}"
    
    return "UNKNOWN_REASON"


def evaluate_sandbox(
    snapshot: Dict[str, Any],
    sandbox_params: SandboxParams,
) -> SandboxResult:
    """Evaluate sandbox selection with hypothetical parameters (Phase 7.5).
    
    This function:
    - Reconstructs ScoredSignalCandidate objects from snapshot
    - Re-runs selection with sandbox parameters
    - Compares with live selected_signals
    - Identifies newly admitted candidates
    
    Args:
        snapshot: DecisionSnapshot dict (from JSON)
        sandbox_params: Sandbox selection parameters
        
    Returns:
        SandboxResult with selected count, signals, and diff analysis
        
    Note:
        This is read-only and does NOT modify the snapshot or any artifacts.
    """
    # Extract scored candidates from snapshot
    scored_candidates_dicts = snapshot.get("scored_candidates")
    if not isinstance(scored_candidates_dicts, list):
        return SandboxResult(
            selected_count=0,
            selected_signals=[],
            newly_admitted=[],
            rejected_reasons={},
        )
    
    # Reconstruct ScoredSignalCandidate objects
    scored_candidates: List[ScoredSignalCandidate] = []
    for scored_dict in scored_candidates_dicts:
        scored = _reconstruct_scored_candidate(scored_dict)
        if scored is not None:
            scored_candidates.append(scored)
    
    if not scored_candidates:
        return SandboxResult(
            selected_count=0,
            selected_signals=[],
            newly_admitted=[],
            rejected_reasons={},
        )
    
    # Build SelectionConfig from sandbox params
    selection_config = SelectionConfig(
        max_total=sandbox_params.max_total,
        max_per_symbol=sandbox_params.max_per_symbol,
        max_per_signal_type=sandbox_params.max_per_signal_type,
        min_score=sandbox_params.min_score,
    )
    
    # Re-run selection with sandbox params
    sandbox_selected, _ = select_signals(scored_candidates, selection_config)
    
    # Convert to dicts for comparison
    sandbox_selected_dicts = []
    for selected in sandbox_selected:
        scored = selected.scored
        sandbox_selected_dicts.append({
            "scored": {
                "rank": scored.rank,
                "score": {
                    "total": scored.score.total,
                    "components": [
                        {"name": c.name, "value": c.value, "weight": c.weight}
                        for c in scored.score.components
                    ],
                },
                "candidate": {
                    "symbol": scored.candidate.symbol,
                    "signal_type": scored.candidate.signal_type.value,
                    "strike": scored.candidate.strike,
                    "expiry": scored.candidate.expiry.isoformat() if isinstance(scored.candidate.expiry, date) else str(scored.candidate.expiry),
                    "bid": scored.candidate.bid,
                    "ask": scored.candidate.ask,
                    "mid": scored.candidate.mid,
                },
            },
            "selection_reason": selected.selection_reason,
        })
    
    # Get live selected signals
    live_selected_dicts = snapshot.get("selected_signals") or []
    if not isinstance(live_selected_dicts, list):
        live_selected_dicts = []
    
    # Build set of live selected keys
    live_selected_keys = set()
    for live_dict in live_selected_dicts:
        key = _candidate_key(live_dict)
        if key:
            live_selected_keys.add(key)
    
    # Find newly admitted candidates (in sandbox but not in live)
    newly_admitted: List[Dict[str, Any]] = []
    rejected_reasons: Dict[str, str] = {}
    
    # Extract live config from explanations
    live_config = {}
    explanations = snapshot.get("explanations") or []
    if explanations and isinstance(explanations, list) and len(explanations) > 0:
        first_expl = explanations[0]
        if isinstance(first_expl, dict):
            policy = first_expl.get("policy_snapshot", {})
            if isinstance(policy, dict):
                live_config = policy
    
    # Map sandbox selected back to ScoredSignalCandidate for rejection analysis
    sandbox_selected_by_key = {}
    for selected in sandbox_selected:
        scored = selected.scored
        key = (scored.candidate.symbol, scored.candidate.signal_type.value,
               scored.candidate.expiry.isoformat() if isinstance(scored.candidate.expiry, date) else str(scored.candidate.expiry),
               scored.candidate.strike)
        sandbox_selected_by_key[key] = scored
    
    for sandbox_dict in sandbox_selected_dicts:
        key = _candidate_key(sandbox_dict)
        if key and key not in live_selected_keys:
            newly_admitted.append(sandbox_dict)
            
            # Determine rejection reason by re-running live selection logic
            scored_candidate = sandbox_selected_by_key.get(key)
            if scored_candidate:
                reason = _determine_rejection_reason(
                    scored_candidate, 
                    live_selected_keys, 
                    live_config,
                    live_selected_dicts,
                )
                rejected_reasons[str(key)] = reason
            else:
                rejected_reasons[str(key)] = "UNKNOWN_REASON"
    
    return SandboxResult(
        selected_count=len(sandbox_selected_dicts),
        selected_signals=sandbox_selected_dicts,
        newly_admitted=newly_admitted,
        rejected_reasons=rejected_reasons,
    )


__all__ = ["SandboxParams", "SandboxResult", "evaluate_sandbox"]
