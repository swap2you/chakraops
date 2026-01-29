"""Signal Viability Analysis (Phase 7.6).

Read-only analysis of upstream data availability issues that prevent
candidates from reaching selection. Observability only, no mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class SymbolViability:
    """Per-symbol viability metrics (Phase 7.6)."""

    symbol: str
    expiries_in_dte_window: int
    puts_scanned: int
    calls_scanned: int
    iv_available: bool
    primary_blockage: str  # One of: DATA_UNAVAILABLE, NO_EXPIRIES_IN_DTE, NO_STRIKES_MATCHING_DELTA, SCORE_TOO_LOW, CONFIG_CAP, VIABLE


def _extract_symbols_from_universe(snapshot: Dict[str, Any]) -> Set[str]:
    """Extract all symbols that were evaluated (Phase 7.6)."""
    symbols: Set[str] = set()
    
    # From coverage_summary
    coverage_summary = snapshot.get("coverage_summary")
    if isinstance(coverage_summary, dict):
        by_symbol = coverage_summary.get("by_symbol", {})
        if isinstance(by_symbol, dict):
            symbols.update(by_symbol.keys())
    
    # From candidates
    candidates = snapshot.get("candidates") or []
    if isinstance(candidates, list):
        for cand in candidates:
            if isinstance(cand, dict):
                symbol = cand.get("symbol")
                if symbol:
                    symbols.add(symbol)
    
    # From scored_candidates
    scored_candidates = snapshot.get("scored_candidates") or []
    if isinstance(scored_candidates, list):
        for scored in scored_candidates:
            if isinstance(scored, dict):
                candidate = scored.get("candidate", {})
                if isinstance(candidate, dict):
                    symbol = candidate.get("symbol")
                    if symbol:
                        symbols.add(symbol)
    
    # From selected_signals
    selected_signals = snapshot.get("selected_signals") or []
    if isinstance(selected_signals, list):
        for selected in selected_signals:
            if isinstance(selected, dict):
                scored = selected.get("scored", {})
                if isinstance(scored, dict):
                    candidate = scored.get("candidate", {})
                    if isinstance(candidate, dict):
                        symbol = candidate.get("symbol")
                        if symbol:
                            symbols.add(symbol)
    
    # From exclusions
    exclusions = snapshot.get("exclusions") or []
    if isinstance(exclusions, list):
        for excl in exclusions:
            if isinstance(excl, dict):
                symbol = excl.get("symbol")
                if symbol:
                    symbols.add(symbol)
    
    return symbols


def _count_expiries_in_dte_window(symbol: str, candidates: List[Dict[str, Any]]) -> int:
    """Count unique expiries in DTE window for a symbol (Phase 7.6)."""
    expiries: Set[str] = set()
    
    for cand in candidates:
        if isinstance(cand, dict) and cand.get("symbol") == symbol:
            expiry = cand.get("expiry")
            if expiry:
                expiries.add(str(expiry))
    
    return len(expiries)


def _count_puts_scanned(symbol: str, candidates: List[Dict[str, Any]]) -> int:
    """Count CSP candidates (PUT options) for a symbol (Phase 7.6)."""
    count = 0
    
    for cand in candidates:
        if isinstance(cand, dict):
            if cand.get("symbol") == symbol:
                signal_type = cand.get("signal_type")
                if isinstance(signal_type, dict):
                    signal_type = signal_type.get("value") or signal_type.get("name")
                if signal_type == "CSP" or cand.get("option_right") == "PUT":
                    count += 1
    
    return count


def _count_calls_scanned(symbol: str, candidates: List[Dict[str, Any]]) -> int:
    """Count CC candidates (CALL options) for a symbol (Phase 7.6)."""
    count = 0
    
    for cand in candidates:
        if isinstance(cand, dict):
            if cand.get("symbol") == symbol:
                signal_type = cand.get("signal_type")
                if isinstance(signal_type, dict):
                    signal_type = signal_type.get("value") or signal_type.get("name")
                if signal_type == "CC" or cand.get("option_right") == "CALL":
                    count += 1
    
    return count


def _check_iv_available(symbol: str, candidates: List[Dict[str, Any]]) -> bool:
    """Check if IV data is available for any candidate of a symbol (Phase 7.6)."""
    for cand in candidates:
        if isinstance(cand, dict) and cand.get("symbol") == symbol:
            iv = cand.get("iv")
            if iv is not None and iv != 0.0:
                return True
    
    return False


def _classify_primary_blockage(
    symbol: str,
    snapshot: Dict[str, Any],
    expiries_in_dte_window: int,
    puts_scanned: int,
    calls_scanned: int,
) -> str:
    """Classify the primary blockage reason for a symbol (Phase 7.6).
    
    Returns one of:
    - DATA_UNAVAILABLE: Chain fetch errors, no expirations
    - NO_EXPIRIES_IN_DTE: No expiries in DTE window
    - NO_STRIKES_MATCHING_DELTA: No strikes matching delta/OTM range
    - SCORE_TOO_LOW: Candidates generated but none selected (score too low)
    - CONFIG_CAP: Config caps prevented selection
    - VIABLE: Symbol produced selected signals
    """
    # Check if symbol has selected signals (VIABLE)
    selected_signals = snapshot.get("selected_signals") or []
    if isinstance(selected_signals, list):
        for selected in selected_signals:
            if isinstance(selected, dict):
                scored = selected.get("scored", {})
                if isinstance(scored, dict):
                    candidate = scored.get("candidate", {})
                    if isinstance(candidate, dict) and candidate.get("symbol") == symbol:
                        return "VIABLE"
    
    # Check exclusions for this symbol
    exclusions = snapshot.get("exclusions") or []
    if isinstance(exclusions, list):
        for excl in exclusions:
            if isinstance(excl, dict) and excl.get("symbol") == symbol:
                rule = excl.get("rule", "").upper()
                stage = excl.get("stage", "")
                
                # DATA_UNAVAILABLE
                if rule in ("CHAIN_FETCH_ERROR", "NO_EXPIRATIONS"):
                    return "DATA_UNAVAILABLE"
                
                # NO_EXPIRIES_IN_DTE
                if rule == "NO_EXPIRY_IN_DTE_WINDOW":
                    return "NO_EXPIRIES_IN_DTE"
                
                # NO_STRIKES_MATCHING_DELTA
                if rule in ("NO_STRIKES_IN_DELTA_RANGE", "NO_STRIKES_IN_OTM_RANGE"):
                    return "NO_STRIKES_MATCHING_DELTA"
    
    # Check coverage summary for this symbol
    coverage_summary = snapshot.get("coverage_summary")
    if isinstance(coverage_summary, dict):
        by_symbol = coverage_summary.get("by_symbol", {})
        if isinstance(by_symbol, dict):
            symbol_coverage = by_symbol.get(symbol, {})
            if isinstance(symbol_coverage, dict):
                generation = symbol_coverage.get("generation", 0)
                scoring = symbol_coverage.get("scoring", 0)
                selection = symbol_coverage.get("selection", 0)
                
                # If candidates generated but none selected, likely SCORE_TOO_LOW
                if generation > 0 and selection == 0:
                    # Check if it's actually a config cap
                    # (This is approximate - we'd need to check near_misses for exact reason)
                    if scoring > 0:
                        # Candidates were scored but not selected
                        # Check if it's a config cap by looking at near_misses
                        near_misses = snapshot.get("near_misses") or []
                        if isinstance(near_misses, list):
                            for nm in near_misses:
                                if isinstance(nm, dict) and nm.get("symbol") == symbol:
                                    failed_rule = nm.get("failed_rule", "")
                                    if "max_per_symbol" in failed_rule.lower() or "max_total" in failed_rule.lower():
                                        return "CONFIG_CAP"
                        return "SCORE_TOO_LOW"
    
    # If we have candidates but no expiries, likely NO_EXPIRIES_IN_DTE
    if (puts_scanned > 0 or calls_scanned > 0) and expiries_in_dte_window == 0:
        return "NO_EXPIRIES_IN_DTE"
    
    # If no candidates at all, check exclusions more carefully
    if puts_scanned == 0 and calls_scanned == 0:
        # Check if there are exclusions indicating data issues
        has_data_exclusions = False
        if isinstance(exclusions, list):
            for excl in exclusions:
                if isinstance(excl, dict) and excl.get("symbol") == symbol:
                    rule = excl.get("rule", "").upper()
                    if rule in ("CHAIN_FETCH_ERROR", "NO_EXPIRATIONS"):
                        has_data_exclusions = True
                        break
        
        if has_data_exclusions:
            return "DATA_UNAVAILABLE"
        
        # Otherwise, likely no expiries or strikes
        if expiries_in_dte_window == 0:
            return "NO_EXPIRIES_IN_DTE"
        else:
            return "NO_STRIKES_MATCHING_DELTA"
    
    # Default: unknown blockage
    return "SCORE_TOO_LOW"


def analyze_signal_viability(snapshot: Dict[str, Any]) -> List[SymbolViability]:
    """Analyze signal viability per symbol (Phase 7.6).
    
    This function:
    - Extracts all symbols from snapshot
    - Computes per-symbol metrics (expiries, puts, calls, IV)
    - Classifies primary blockage reason
    
    Args:
        snapshot: DecisionSnapshot dict (from JSON)
        
    Returns:
        List of SymbolViability objects, one per symbol
        
    Note:
        This is read-only and does NOT modify the snapshot.
    """
    symbols = _extract_symbols_from_universe(snapshot)
    
    if not symbols:
        return []
    
    candidates = snapshot.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    
    viability_list: List[SymbolViability] = []
    
    for symbol in sorted(symbols):
        expiries_in_dte_window = _count_expiries_in_dte_window(symbol, candidates)
        puts_scanned = _count_puts_scanned(symbol, candidates)
        calls_scanned = _count_calls_scanned(symbol, candidates)
        iv_available = _check_iv_available(symbol, candidates)
        
        primary_blockage = _classify_primary_blockage(
            symbol,
            snapshot,
            expiries_in_dte_window,
            puts_scanned,
            calls_scanned,
        )
        
        viability_list.append(
            SymbolViability(
                symbol=symbol,
                expiries_in_dte_window=expiries_in_dte_window,
                puts_scanned=puts_scanned,
                calls_scanned=calls_scanned,
                iv_available=iv_available,
                primary_blockage=primary_blockage,
            )
        )
    
    return viability_list


__all__ = ["SymbolViability", "analyze_signal_viability"]
