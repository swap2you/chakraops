# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) read model — cheap, authoritative reads over the published
snapshot ONLY. No provider calls, no full recompute.

Every function reads ``snapshot_latest.json`` via :mod:`store`. Missing/corrupt snapshot
is reported fail-closed as ``status="NO_SNAPSHOT"`` with empty collections.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.universe_v2 import store
from app.core.universe_v2.model import (
    ALL_STRATEGIES,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    MEMBERSHIP_NOT_EVALUATED,
    UniverseV2Snapshot,
)

STALE_SECONDS = int(os.getenv("UNIVERSE_V2_STALE_SECONDS", "86400"))
NO_SNAPSHOT = "NO_SNAPSHOT"


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _freshness_fields(snap: UniverseV2Snapshot) -> Dict[str, Any]:
    created = _parse_iso(snap.created_at_utc)
    age: Optional[float] = None
    stale = False
    if created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - created).total_seconds()
        stale = age > STALE_SECONDS
    return {
        "version": snap.version,
        "status": snap.status,
        "created_at_utc": snap.created_at_utc,
        "source_evaluation_version": snap.source_evaluation_version,
        "age_seconds": age,
        "stale": stale,
    }


def _empty(kind: str) -> Dict[str, Any]:
    base = {"status": NO_SNAPSHOT, "version": 0, "created_at_utc": None}
    if kind == "summary":
        base.update({
            "research_pool_count": 0,
            "lifecycle_funnel": {},
            "strategy_eligible": {s: 0 for s in ALL_STRATEGIES},
            "top_rejection_reasons": [],
            "stale": True,
        })
    return base


def summary() -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return _empty("summary")
    counts = snap.counts or {}
    out = _freshness_fields(snap)
    out.update({
        "research_pool_count": snap.research_pool_count,
        "lifecycle_funnel": counts.get("lifecycle_funnel", {}),
        "strategy_eligible": counts.get("strategy_eligible", {s: 0 for s in ALL_STRATEGIES}),
        "strategy_not_eligible": counts.get("strategy_not_eligible", {}),
        "top_rejection_reasons": counts.get("top_rejection_reasons", []),
        "total_records": counts.get("total_records", len(snap.records)),
    })
    return out


def research_pool() -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "count": 0, "symbols": []}
    symbols = sorted(r.symbol for r in snap.records if r.in_research_pool)
    return {
        "status": snap.status,
        "version": snap.version,
        "count": len(symbols),
        "symbols": symbols,
    }


def records(
    page: int = 1,
    page_size: int = 100,
    lifecycle: Optional[str] = None,
    strategy: Optional[str] = None,
    membership_status: Optional[str] = None,
) -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "version": 0, "page": page, "page_size": page_size,
                "total": 0, "records": []}
    recs = snap.records
    if lifecycle:
        lc = lifecycle.strip().upper()
        recs = [r for r in recs if r.lifecycle_state == lc]
    if strategy:
        # A strategy filter is meaningful on its own: default to that strategy's ELIGIBLE
        # members; combine with membership_status to view NOT_ELIGIBLE/NOT_EVALUATED sets.
        st = strategy.strip().upper()
        ms = (membership_status or MEMBERSHIP_ELIGIBLE).strip().upper()
        recs = [r for r in recs if st in r.memberships and r.memberships[st].status == ms]
    total = len(recs)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 1000))
    start = (page - 1) * page_size
    window = recs[start:start + page_size]
    return {
        "status": snap.status,
        "version": snap.version,
        "created_at_utc": snap.created_at_utc,
        "page": page,
        "page_size": page_size,
        "total": total,
        "records": [r.to_dict() for r in window],
    }


def record(symbol: str) -> Optional[Dict[str, Any]]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return None
    sym = (symbol or "").strip().upper()
    for r in snap.records:
        if r.symbol == sym:
            d = r.to_dict()
            # Attach full transition history from durable state.
            state = store.load_state()
            sym_state = (state.get("symbols") or {}).get(sym) or {}
            d["transition_history"] = sym_state.get("transitions") or []
            d["version"] = snap.version
            return d
    return None


def membership(strategy: str) -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    st = (strategy or "").strip().upper()
    if snap is None:
        return {"status": NO_SNAPSHOT, "strategy": st, "eligible": [], "not_eligible": [], "not_evaluated": []}
    eligible: List[str] = []
    not_eligible: List[Dict[str, Any]] = []
    not_evaluated: List[str] = []
    for r in snap.records:
        m = r.memberships.get(st)
        if not m:
            continue
        if m.status == MEMBERSHIP_ELIGIBLE:
            eligible.append(r.symbol)
        elif m.status == MEMBERSHIP_NOT_ELIGIBLE:
            not_eligible.append({"symbol": r.symbol, "reason": m.primary_reason})
        elif m.status == MEMBERSHIP_NOT_EVALUATED:
            not_evaluated.append(r.symbol)
    return {
        "status": snap.status,
        "version": snap.version,
        "strategy": st,
        "eligible": sorted(eligible),
        "not_eligible": sorted(not_eligible, key=lambda x: x["symbol"]),
        "not_evaluated": sorted(not_evaluated),
    }


def rejections() -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "funnel": {}, "top_reasons": []}
    counts = snap.counts or {}
    return {
        "status": snap.status,
        "version": snap.version,
        "funnel": {
            "strategy_eligible": counts.get("strategy_eligible", {}),
            "strategy_not_eligible": counts.get("strategy_not_eligible", {}),
            "lifecycle_funnel": counts.get("lifecycle_funnel", {}),
        },
        "top_reasons": counts.get("top_rejection_reasons", []),
    }


def near_misses() -> Dict[str, Any]:
    """Deterministic near-misses: WATCH symbols with a temporary (soft) reason and NO
    safety-critical failure. Never includes quarantined/safety-critical symbols."""
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "version": 0, "near_misses": []}
    out: List[Dict[str, Any]] = []
    for r in snap.records:
        if r.lifecycle_state == LIFECYCLE_WATCH and r.temporary and not r.safety_critical:
            out.append({"symbol": r.symbol, "reason": r.primary_reason})
    return {"status": snap.status, "version": snap.version,
            "near_misses": sorted(out, key=lambda x: x["symbol"])}


def transitions(limit: int = 50) -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "version": 0, "transitions": []}
    items: List[Dict[str, Any]] = []
    for r in snap.records:
        if r.last_transition is not None:
            t = r.last_transition.to_dict()
            t["symbol"] = r.symbol
            items.append(t)
    items.sort(key=lambda x: (x.get("at_utc") or ""), reverse=True)
    return {"status": snap.status, "version": snap.version, "transitions": items[: max(1, int(limit))]}


def freshness() -> Dict[str, Any]:
    snap = store.get_latest_snapshot()
    if snap is None:
        return {"status": NO_SNAPSHOT, "version": 0, "stale": True, "age_seconds": None,
                "created_at_utc": None}
    return _freshness_fields(snap)
