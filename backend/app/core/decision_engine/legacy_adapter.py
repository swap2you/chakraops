# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Adapter: canonical ``DecisionOutput`` -> live UI shapes (R34.0).

The canonical decision engine is the authoritative producer of the primary live
recommendation. This adapter maps its output to the shapes the live UI consumes
(action codes, item dicts) WITHOUT leaking raw ``FAIL_``/``WARN_`` labels and
without the legacy evaluator independently producing a conflicting primary
action. Every item is tagged ``authoritative=True`` and ``manual_only=True`` and
records ``recommended_by="canonical_decision_engine"``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.decision_engine.contract import (
    ACTIONABLE,
    BLOCKED,
    DecisionOutput,
    STAY_IN_CASH,
    WATCH,
)

DECISION_SOURCE = "canonical_decision_engine"

# Canonical decision status -> live action code surfaced to the operator.
STATUS_TO_ACTION_CODE: Dict[str, str] = {
    ACTIONABLE: "ENTRY",
    WATCH: "WATCH",
    BLOCKED: "BLOCKED",
    STAY_IN_CASH: "STAY_IN_CASH",
}


def _safe_reason_codes(codes: List[str]) -> List[str]:
    """Strip any raw FAIL_/WARN_ prefixes so they never reach UI JSON."""
    out: List[str] = []
    for c in codes or []:
        s = str(c)
        if s.startswith("FAIL_"):
            s = s[5:]
        elif s.startswith("WARN_"):
            s = s[5:]
        out.append(s)
    return out


def to_live_item(o: DecisionOutput) -> Dict[str, Any]:
    """Map one canonical ``DecisionOutput`` to a live action item."""
    return {
        "symbol": o.symbol,
        "strategy": o.strategy,
        "profile": o.profile,
        "market_regime": o.market_regime,
        "next_action_code": STATUS_TO_ACTION_CODE.get(o.decision_status, "NONE"),
        "decision_status": o.decision_status,
        "eligibility": o.eligibility,
        "data_quality": o.data_quality,
        "data_freshness": o.data_freshness,
        "event_risk": o.event_risk,
        "selected_contract": o.selected_contract,
        "sizing": o.sizing,
        "recommended_contracts": o.sizing.get("contracts") if isinstance(o.sizing, dict) else None,
        "recommended_shares": o.sizing.get("shares") if isinstance(o.sizing, dict) else None,
        "capital_required": o.capital_required,
        "expected_return_pct": o.expected_return_pct,
        "expected_return_dollars": o.expected_return_dollars,
        "risk_flags": _safe_reason_codes(o.risk_flags),
        "score": o.score,
        "rank": o.rank,
        "reason_codes": _safe_reason_codes(o.reason_codes),
        "manual_only": True,
        "authoritative": True,
        "recommended_by": DECISION_SOURCE,
    }


def to_live_recommendations(result: Dict[str, Any]) -> Dict[str, Any]:
    """Map the engine.evaluate() result dict into live, labeled lists.

    ``result`` is the dict returned by ``decision_engine.engine.evaluate``;
    its ``actionable``/``watch``/``blocked`` entries are already ``DecisionOutput``
    dicts. This re-shapes them for the UI and preserves the authoritative tag.
    """

    def _wrap(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for d in items:
            out.append(
                {
                    "symbol": d.get("symbol"),
                    "strategy": d.get("strategy"),
                    "profile": d.get("profile"),
                    "market_regime": d.get("market_regime"),
                    "next_action_code": STATUS_TO_ACTION_CODE.get(d.get("decision_status"), "NONE"),
                    "decision_status": d.get("decision_status"),
                    "eligibility": d.get("eligibility"),
                    "data_quality": d.get("data_quality"),
                    "data_freshness": d.get("data_freshness"),
                    "event_risk": d.get("event_risk"),
                    "selected_contract": d.get("selected_contract"),
                    "sizing": d.get("sizing"),
                    "recommended_contracts": (d.get("sizing") or {}).get("contracts"),
                    "recommended_shares": (d.get("sizing") or {}).get("shares"),
                    "capital_required": d.get("capital_required"),
                    "expected_return_pct": d.get("expected_return_pct"),
                    "expected_return_dollars": d.get("expected_return_dollars"),
                    "risk_flags": _safe_reason_codes(d.get("risk_flags") or []),
                    "score": d.get("score"),
                    "rank": d.get("rank"),
                    "reason_codes": _safe_reason_codes(d.get("reason_codes") or []),
                    "manual_only": True,
                    "authoritative": True,
                    "recommended_by": DECISION_SOURCE,
                }
            )
        return out

    return {
        "decision_source": DECISION_SOURCE,
        "manual_only": True,
        "profile": result.get("profile"),
        "as_of_utc": result.get("as_of_utc"),
        "actionable": _wrap(result.get("actionable") or []),
        "watch": _wrap(result.get("watch") or []),
        "blocked": _wrap(result.get("blocked") or []),
        "stay_in_cash": result.get("stay_in_cash"),
        "counts": result.get("counts"),
    }
