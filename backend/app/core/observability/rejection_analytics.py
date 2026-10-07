# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Rejection analytics and heatmaps (Phase 5.2).

Aggregate rejection reasons across symbols and time.
Stages: REGIME, ENVIRONMENT, SELECTION, PORTFOLIO.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

# DecisionSnapshot may be dataclass or dict
from app.signals.decision_snapshot import DecisionSnapshot

# Stage buckets for analytics (Phase 5.2)
STAGES = ("REGIME", "ENVIRONMENT", "SELECTION", "PORTFOLIO")


def _code_to_stage(code: str) -> str:
    """Map rejection code to stage: REGIME, ENVIRONMENT, SELECTION, PORTFOLIO."""
    c = (code or "").strip().upper()
    # REGIME: volatility / snapshot / execution gate (no signals, stale)
    if c in ("SNAPSHOT_STALE", "SNAPSHOT_AS_OF_INVALID", "NO_SYMBOLS_EVALUATED", "NO_SELECTED_SIGNALS"):
        if c == "NO_SELECTED_SIGNALS":
            return "SELECTION"  # no signals selected is selection funnel
        return "REGIME"
    # ENVIRONMENT: earnings, macro, session, data completeness
    if c in ("EARNINGS_WINDOW", "MACRO_EVENT_WINDOW", "SHORT_SESSION", "INSUFFICIENT_TRADING_DAYS", "DATA_INCOMPLETE"):
        return "ENVIRONMENT"
    # PORTFOLIO: caps
    if c in ("MAX_POSITIONS", "RISK_BUDGET", "SECTOR_CAP", "DELTA_EXPOSURE"):
        return "PORTFOLIO"
    # SELECTION: context gating, confidence, generation exclusions
    if c in (
        "IV_RANK_LOW_SELL", "IV_RANK_HIGH_SELL", "IV_RANK_HIGH_BUY",
        "EXPECTED_MOVE_EXCEEDS_STRIKE_DISTANCE", "EVENT_WITHIN_WINDOW",
        "CONFIDENCE_BELOW_THRESHOLD", "CHAIN_FETCH", "NORMALIZATION",
        "CSP_GENERATION", "CC_GENERATION", "NO_EXPIRATIONS", "NO_OPTIONS_FOR_SYMBOL",
        "NO_EXPIRY_IN_DTE_WINDOW", "NO_LIQUID_PUTS", "NO_LIQUID_CALLS",
        "NO_STRIKES_IN_OTM_RANGE", "NO_STRIKES_IN_DELTA_RANGE", "NO_UNDERLYING_PRICE",
        "MISSING_REQUIRED_FIELD", "INVALID_EXPIRY", "INVALID_STRIKE",
        "SIGNAL_SCORE_BELOW_MIN", "SELECTED_COUNT_EXCEEDS_MAX",
    ):
        return "SELECTION"
    return "SELECTION"  # default unknown to SELECTION


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Convert DecisionSnapshot or dict to dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    return {}


def summarize_rejections(
    decision_snapshot: DecisionSnapshot | Dict[str, Any],
    gate_result: Any = None,
) -> Dict[str, Any]:
    """Summarize rejection reasons from a decision snapshot (and optional gate result).

    Returns:
    - by_reason: Dict[reason_code, count]
    - by_stage: Dict[stage, count] for REGIME, ENVIRONMENT, SELECTION, PORTFOLIO
    - symbol_frequency: List[Dict] with symbol, reason, count (or symbol -> {reason: count})
    """
    snapshot = _as_dict(decision_snapshot)
    exclusions = snapshot.get("exclusions") or []
    stats = snapshot.get("stats") or {}

    by_reason: Counter = Counter()
    by_stage: Counter = Counter()
    symbol_reasons: Dict[str, Counter] = defaultdict(Counter)

    # From snapshot exclusions (each has rule/code, symbol, stage)
    for excl in exclusions:
        if not isinstance(excl, dict):
            continue
        code = excl.get("rule") or excl.get("code") or "UNKNOWN"
        data = excl.get("data")
        symbol = excl.get("symbol") or excl.get("Symbol") or (data.get("symbol") if isinstance(data, dict) else None) or "UNKNOWN"
        by_reason[code] += 1
        stage = _code_to_stage(code)
        by_stage[stage] += 1
        symbol_reasons[symbol or "UNKNOWN"][code] += 1

    # From gate_result.reasons (execution gate blocking codes)
    if gate_result is not None:
        reasons = getattr(gate_result, "reasons", None) or []
        if isinstance(reasons, list):
            for r in reasons:
                if isinstance(r, str) and r.strip():
                    code = r.strip()
                    by_reason[code] += 1
                    stage = _code_to_stage(code)
                    by_stage[stage] += 1
                    # Gate reasons often apply to "selected" symbol; use generic or leave symbol_frequency from exclusions only
                    symbol_reasons["_gate"][code] += 1

    # Symbol-frequency table: list of {symbol, reason, count}
    symbol_frequency: List[Dict[str, Any]] = []
    for sym, reason_counts in sorted(symbol_reasons.items()):
        for reason, count in reason_counts.most_common():
            symbol_frequency.append({"symbol": sym, "reason": reason, "count": count})

    return {
        "by_reason": dict(by_reason),
        "by_stage": {s: by_stage.get(s, 0) for s in STAGES},
        "symbol_frequency": symbol_frequency,
        "symbols_considered": int(stats.get("symbols_evaluated", 0)),
        "total_rejections": sum(by_reason.values()),
    }


def compute_rejection_heatmap(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute heatmap aggregates from a list of daily (or per-run) rejection summaries.

    history: list of dicts from summarize_rejections (each may have by_reason, by_stage, symbol_frequency).

    Returns:
    - dates: list of date/identifier keys if present
    - reason_totals: aggregate count by reason across all history
    - stage_totals: aggregate count by stage
    - symbol_totals: aggregate count by symbol (total rejections per symbol)
    - matrix: optional list of {date, by_reason} for heatmap rows
    """
    reason_totals: Counter = Counter()
    stage_totals: Counter = Counter()
    symbol_totals: Counter = Counter()
    dates: List[str] = []
    matrix: List[Dict[str, Any]] = []

    for i, summary in enumerate(history):
        if not isinstance(summary, dict):
            continue
        date_key = summary.get("date") or summary.get("as_of") or f"run_{i}"
        dates.append(str(date_key))
        by_reason = summary.get("by_reason") or {}
        by_stage = summary.get("by_stage") or {}
        symbol_freq = summary.get("symbol_frequency") or []
        for code, count in by_reason.items():
            reason_totals[code] += count
        for stage, count in by_stage.items():
            stage_totals[stage] += count
        for row in symbol_freq:
            sym = row.get("symbol")
            if sym and sym != "_gate":
                symbol_totals[sym] += int(row.get("count", 0))
        matrix.append({"date": date_key, "by_reason": by_reason})

    return {
        "dates": dates,
        "reason_totals": dict(reason_totals),
        "stage_totals": {s: stage_totals.get(s, 0) for s in STAGES},
        "symbol_totals": dict(symbol_totals),
        "matrix": matrix,
    }
