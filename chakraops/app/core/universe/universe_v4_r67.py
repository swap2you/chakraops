# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R67 Universe V4 weekly discovery helper — explainable; no threshold retune."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.core.universe.event_intelligence_r67 import gate_symbol_for_events
from app.core.universe.screener_v3_r55 import screen_universe_v3


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


ELIGIBILITY_BUCKETS = ("wheel", "stock", "etf_hedge", "research")


def _explain_transition(
    *,
    symbol: str,
    prior_state: str,
    new_state: str,
    reason: str,
    source: str,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "prior_state": prior_state,
        "new_state": new_state,
        "reason": reason,
        "source": source,
        "timestamp": _utc_now_iso(),
    }


def weekly_discovery_v4(
    candidates: List[Dict[str, Any]],
    *,
    prior_states: Optional[Dict[str, str]] = None,
    min_liquidity_rank: Optional[float] = None,
    require_options_for_wheel: bool = True,
    earnings_within_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Idempotent weekly discovery/admission helper.

    - Dedupes symbols
    - Rejects IV-only junk (IV without liquidity / options when required)
    - Event-aware gating with provenance
    - Never retunes production thresholds
    """
    prior = {str(k).upper(): str(v) for k, v in (prior_states or {}).items()}
    seen: Set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for row in candidates or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        deduped.append(dict(row, symbol=sym))

    screen = screen_universe_v3(
        deduped,
        min_liquidity_rank=min_liquidity_rank,
        require_options=False,
    )

    admissions: List[Dict[str, Any]] = []
    removals: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    buckets: Dict[str, List[str]] = {b: [] for b in ELIGIBILITY_BUCKETS}

    for row in screen.get("rows") or []:
        sym = row["symbol"]
        prior_state = prior.get(sym, "ABSENT")
        reasons = list(row.get("reasons") or [])
        inputs = row.get("inputs") or {}

        # IV-only junk: iv_rank present but no liquidity and no options → reject.
        iv_only = bool(inputs.get("iv_rank") is not None or row.get("iv_rank") is not None)
        # Prefer candidate row extras if present on original
        src = next((c for c in deduped if c["symbol"] == sym), {})
        iv_rank = src.get("iv_rank", inputs.get("iv_rank"))
        has_options = bool(src.get("has_options") or inputs.get("has_options"))
        liq = src.get("liquidity_rank", inputs.get("liquidity_rank"))
        is_etf = bool(src.get("is_etf"))
        earnings_date = src.get("earnings_date")

        if iv_rank is not None and liq is None and not has_options:
            new_state = "REJECTED"
            reason = "iv_only_junk_rejected"
            reasons.append(reason)
            removals.append(
                {
                    "symbol": sym,
                    "state": new_state,
                    "reasons": reasons,
                    "explainability": _explain_transition(
                        symbol=sym,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason=reason,
                        source="universe_v4_r67",
                    ),
                }
            )
            transitions.append(removals[-1]["explainability"])
            continue

        if not row.get("include"):
            new_state = "REJECTED"
            reason = "screen_v3_exclude"
            removals.append(
                {
                    "symbol": sym,
                    "state": new_state,
                    "reasons": reasons,
                    "explainability": _explain_transition(
                        symbol=sym,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason=reason,
                        source="universe_screener_v3",
                    ),
                }
            )
            transitions.append(removals[-1]["explainability"])
            continue

        event_gate = gate_symbol_for_events(
            sym,
            earnings_within_days=earnings_within_days,
            earnings_date=str(earnings_date) if earnings_date else None,
        )

        membership: Dict[str, bool] = {
            "research": True,
            "stock": True,
            "wheel": bool(has_options) if require_options_for_wheel else True,
            "etf_hedge": is_etf,
        }
        if require_options_for_wheel and not has_options:
            reasons.append("wheel_requires_options")

        if event_gate.get("action") == "HOLD":
            new_state = "EVENT_HOLD"
            reasons.append("event_gate_hold")
        elif event_gate.get("action") == "ADVISORY":
            new_state = "ADMITTED_ADVISORY"
            reasons.append("event_gate_advisory")
        else:
            new_state = "ADMITTED"

        for bucket, ok in membership.items():
            if ok and new_state.startswith("ADMITTED"):
                buckets[bucket].append(sym)

        explain = _explain_transition(
            symbol=sym,
            prior_state=prior_state,
            new_state=new_state,
            reason=";".join(reasons) or "admitted",
            source="universe_v4_r67",
        )
        transitions.append(explain)
        admissions.append(
            {
                "symbol": sym,
                "state": new_state,
                "membership": membership,
                "reasons": reasons,
                "event_gate": event_gate,
                "explainability": explain,
            }
        )

    return {
        "schema": "universe_discovery_v4_r67",
        "as_of": _utc_now_iso(),
        "idempotent": True,
        "duplicate_symbols_removed": len(candidates or []) - len(deduped),
        "threshold_retune": False,
        "buckets": buckets,
        "admissions": admissions,
        "removals": removals,
        "transitions": transitions,
        "screen_provenance": screen.get("provenance"),
        "manual_only": True,
        "trade_execution": False,
    }


def evaluate_candidate_v4(
    candidate: Dict[str, Any],
    *,
    events: Optional[List[Dict[str, Any]]] = None,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """Single-candidate evaluate helper used by golive API + unit tests."""
    result = weekly_discovery_v4(
        [candidate],
        prior_states={str(candidate.get("symbol") or "").upper(): str(candidate.get("prior_state") or "UNKNOWN")},
        earnings_within_days=7 if events else None,
    )
    admissions = result.get("admissions") or []
    removals = result.get("removals") or []
    row = admissions[0] if admissions else (removals[0] if removals else None)
    if not row:
        # Fall back to lightweight local gate when discovery returns empty
        sym = str(candidate.get("symbol") or "").upper().strip()
        state = "ADMIT"
        reasons: List[str] = []
        if events:
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                et = str(ev.get("event_type") or "").lower()
                if et in {"earnings", "fomc", "cpi", "jobs"} and int(ev.get("within_days") or 99) <= 7:
                    state = "QUARANTINE"
                    reasons.append(f"event_gate:{et}")
        return {
            "symbol": sym,
            "prior_state": str(candidate.get("prior_state") or "UNKNOWN"),
            "state": state,
            "reasons": reasons or ["passed_v4_gates"],
            "as_of": as_of or _utc_now_iso(),
            "threshold_retune": False,
            "manual_only": True,
            "trade_execution": False,
            "provenance": "universe_v4_event_intelligence",
        }
    state = str(row.get("state") or "REJECT")
    if state.startswith("ADMITTED"):
        mapped = "ADMIT"
    elif "EVENT" in state or "HOLD" in state or "QUARANTINE" in state:
        mapped = "QUARANTINE"
    else:
        mapped = "REJECT" if state in {"REJECTED", "REMOVED", "REJECT"} else state
    # If caller supplied explicit events list, prefer event quarantine semantics.
    if events:
        for ev in events:
            if isinstance(ev, dict) and str(ev.get("event_type") or "").lower() in {
                "earnings",
                "fomc",
                "cpi",
                "jobs",
            } and int(ev.get("within_days") or 99) <= 7:
                mapped = "QUARANTINE"
                break
    return {
        "symbol": row.get("symbol"),
        "prior_state": (row.get("explainability") or {}).get("prior_state") or "UNKNOWN",
        "state": mapped,
        "reasons": list(row.get("reasons") or []),
        "as_of": as_of or result.get("as_of") or _utc_now_iso(),
        "threshold_retune": False,
        "manual_only": True,
        "trade_execution": False,
        "provenance": "universe_v4_event_intelligence",
    }
