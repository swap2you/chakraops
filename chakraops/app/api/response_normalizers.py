# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase UI-2: API response normalization — consistent keys at API boundary without logic changes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _ensure_final_verdict(obj: Dict[str, Any]) -> None:
    """Ensure final_verdict exists; copy from verdict or status if missing."""
    if "final_verdict" not in obj or obj["final_verdict"] is None:
        obj["final_verdict"] = obj.get("verdict") or obj.get("status")


def _ensure_score(obj: Dict[str, Any]) -> None:
    """Ensure score exists; copy from composite_score if missing."""
    if "score" not in obj or obj["score"] is None:
        obj["score"] = obj.get("composite_score")


def _best_expiration(obj: Dict[str, Any]) -> Optional[str]:
    """Pick best expiration as ISO string from expiry/expir_date/expiration."""
    for k in ("expiration", "expiry", "expir_date"):
        v = obj.get(k)
        if v is not None and str(v).strip():
            s = str(v).strip()[:10]
            if len(s) >= 10:
                return s
    return None


def _normalize_selected_contract(sc: Any) -> Dict[str, Any]:
    """
    Return consistent selected_contract shape:
    { strike, expiration, dte, delta, bid, ask, open_interest, volume }
    Preserve raw under raw key.
    """
    if sc is None:
        return {"strike": None, "expiration": None, "dte": None, "delta": None, "bid": None, "ask": None, "open_interest": None, "volume": None}
    if isinstance(sc, dict):
        raw = dict(sc)
        contract = sc.get("contract", sc) if "contract" in sc else sc
        if isinstance(contract, dict):
            c = contract
        else:
            c = getattr(contract, "__dict__", {}) or {}
            if not isinstance(c, dict):
                c = {}
        exp = _best_expiration(c) or _best_expiration(sc)
        return {
            "strike": c.get("strike") or sc.get("strike"),
            "expiration": exp,
            "dte": c.get("dte") or sc.get("dte"),
            "delta": c.get("delta") or sc.get("delta"),
            "bid": c.get("bid") or sc.get("bid"),
            "ask": c.get("ask") or sc.get("ask"),
            "open_interest": c.get("open_interest") or sc.get("open_interest"),
            "volume": c.get("volume") or sc.get("volume"),
            "raw": raw,
        }
    return {"strike": None, "expiration": None, "dte": None, "delta": None, "bid": None, "ask": None, "open_interest": None, "volume": None}


def normalize_latest_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize latest-run response: final_verdict, score, expiration, selected_contract shape.
    Preserve originals; backward compatible.
    """
    out = dict(payload)
    top_ranked = out.get("top_ranked") or []
    normalized: List[Dict[str, Any]] = []
    for r in top_ranked:
        row = dict(r)
        _ensure_final_verdict(row)
        _ensure_score(row)
        if "status" in row and "final_verdict" not in row:
            row["final_verdict"] = row["status"]
        exp = row.get("expiration") or _best_expiration(row)
        if exp and not row.get("expiration"):
            row["expiration"] = exp
        normalized.append(row)
    out["top_ranked"] = normalized
    return out


def normalize_symbol_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize symbol drilldown: final_verdict, score, expiration, selected_contract.
    """
    if payload.get("error"):
        return payload
    out = dict(payload)
    # Top-level symbol verdict/score from stage2
    s2 = out.get("stage2") or {}
    s2n = dict(s2)
    _ensure_score(s2n)
    el = s2n.get("eligibility") or {}
    if isinstance(el, dict):
        fv = el.get("status") or s2n.get("band")
        if fv:
            s2n.setdefault("final_verdict", fv)
    out["stage2"] = s2n

    # Normalize candidate_contract / selected_contract
    cand = s2n.get("candidate_contract") or s2n.get("selected_contract") or {}
    s2n["selected_contract"] = _normalize_selected_contract(cand)
    if "candidate_contract" not in s2n:
        s2n["candidate_contract"] = s2n["selected_contract"]

    out["stage2"] = s2n
    out.setdefault("final_verdict", s2n.get("final_verdict") or el.get("status") if isinstance(el, dict) else None)
    out.setdefault("score", s2n.get("score"))
    return out


def normalize_universe_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize universe response: ensure symbols have expiration when available.
    """
    out = dict(payload)
    symbols = out.get("symbols") or []
    normalized: List[Dict[str, Any]] = []
    for s in symbols:
        row = dict(s)
        _ensure_final_verdict(row)
        _ensure_score(row)
        exp = _best_expiration(row)
        if exp and not row.get("expiration"):
            row["expiration"] = exp
        normalized.append(row)
    out["symbols"] = normalized
    return out
