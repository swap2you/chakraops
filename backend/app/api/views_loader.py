# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: Load view models from decision_latest.json + persistence for API.

v2-only: Reads from canonical path <REPO_ROOT>/out/decision_latest.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from app.core.eval.evaluation_store_v2 import get_decision_store_path
except ImportError:
    def get_decision_store_path() -> Path:
        return Path("out") / "decision_latest.json"


def _decision_latest_path() -> Path:
    """Canonical decision store path — ONE source of truth."""
    return get_decision_store_path()


def load_decision_artifact() -> Optional[Dict[str, Any]]:
    """Load decision_latest.json from canonical path. Returns None if missing or invalid. v2-only."""
    p = _decision_latest_path()
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_daily_overview_from_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Build daily-overview dict from v2 artifact (metadata, symbols, selected_candidates)."""
    meta = artifact.get("metadata") or {}
    symbols = artifact.get("symbols") or []
    selected = artifact.get("selected_candidates") or []
    ts = meta.get("pipeline_timestamp") or ""
    date_str = str(ts)[:10] if ts else ""
    links: Dict[str, Any] = {}
    if ts:
        links["latest_decision_ts"] = ts
    eligible_count = int(meta.get("eligible_count", 0) or sum(
        1 for s in symbols if (s.get("verdict") or "").upper() == "ELIGIBLE"
    ))
    # Derive top blockers from primary_reason of HOLD/BLOCKED symbols
    blockers: List[Dict[str, Any]] = []
    for s in symbols:
        v = (s.get("verdict") or "").upper()
        if v in ("HOLD", "BLOCKED"):
            reason = s.get("primary_reason") or ""
            if reason:
                blockers.append({"code": v, "reason": reason})
    why_summary = blockers[0]["reason"] if blockers else ""
    return {
        "date": date_str,
        "run_mode": meta.get("mode") or "DRY_RUN",
        "config_frozen": meta.get("config_frozen", False),
        "freeze_violation_changed_keys": list(meta.get("freeze_violation_changed_keys") or []),
        "regime": meta.get("regime"),
        "regime_reason": meta.get("regime_reason"),
        "symbols_evaluated": len(symbols) or int(meta.get("universe_size", 0)),
        "selected_signals": len(selected),
        "trades_ready": eligible_count,
        "no_trade": eligible_count == 0,
        "why_summary": str(why_summary),
        "top_blockers": blockers[:5],
        "risk_posture": str(meta.get("risk_posture") or "CONSERVATIVE"),
        "links": links,
    }


def get_positions_for_api() -> List[Dict[str, Any]]:
    """Build positions list from persistence (view format). Returns [] on error."""
    try:
        from app.core.persistence import list_open_positions, get_position_events
        from app.ui_contracts.view_builders import build_position_view
        positions = list_open_positions()
        out = []
        for pos in positions:
            events = get_position_events(getattr(pos, "id", pos) if hasattr(pos, "id") else str(pos))
            if hasattr(events, "__iter__") and not isinstance(events, dict):
                events = list(events) if events else []
            else:
                events = []
            try:
                v = build_position_view(pos, events)
                out.append(v.to_dict() if hasattr(v, "to_dict") else v.__dict__)
            except Exception:
                continue
        return out
    except Exception:
        return []


def get_alerts_for_api(daily_overview: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build alerts view from persistence events + daily overview. Returns as_of + items."""
    from datetime import datetime, timezone
    as_of = datetime.now(timezone.utc).isoformat()
    items: List[Dict[str, Any]] = []
    try:
        from app.core.persistence import get_recent_position_events
        events = get_recent_position_events(days=7)
        for e in events or []:
            et = e.get("event_type") or ""
            pid = e.get("position_id")
            if et == "TARGET_1_HIT":
                items.append({
                    "level": "info",
                    "code": "PROFIT_TARGET_HIT",
                    "message": "Profit target hit",
                    "symbol": (e.get("metadata") or {}).get("symbol", ""),
                    "position_id": pid,
                    "decision_ts": None,
                })
            elif et == "STOP_TRIGGERED":
                items.append({
                    "level": "warning",
                    "code": "STOP_TRIGGERED",
                    "message": "Stop triggered",
                    "symbol": (e.get("metadata") or {}).get("symbol", ""),
                    "position_id": pid,
                    "decision_ts": None,
                })
    except Exception:
        pass
    if daily_overview:
        if daily_overview.get("freeze_violation_changed_keys"):
            items.append({
                "level": "error",
                "code": "FREEZE_VIOLATION",
                "message": f"Config changed: {', '.join(daily_overview['freeze_violation_changed_keys'])}",
                "symbol": "",
                "position_id": None,
                "decision_ts": daily_overview.get("links", {}).get("latest_decision_ts"),
            })
        if daily_overview.get("no_trade") and daily_overview.get("top_blockers"):
            top = daily_overview["top_blockers"][0] if daily_overview["top_blockers"] else {}
            items.append({
                "level": "info",
                "code": "NO_TRADE",
                "message": f"No trade; top blocker: {top.get('code', 'NO_TRADE')}",
                "symbol": "",
                "position_id": None,
                "decision_ts": daily_overview.get("links", {}).get("latest_decision_ts"),
            })
    return {"as_of": as_of, "items": items}


def get_decision_history_for_api() -> List[Dict[str, Any]]:
    """Build decision-history list from v2 artifact. Returns [] on error."""
    artifact = load_decision_artifact()
    if not artifact:
        return []
    overview = build_daily_overview_from_artifact(artifact)
    meta = artifact.get("metadata") or {}
    ts = meta.get("pipeline_timestamp") or ""
    date_str = str(ts)[:10] if ts else overview.get("date", "")
    eligible = overview.get("trades_ready", 0) or meta.get("eligible_count", 0)
    outcome = "NO_TRADE" if eligible == 0 else "TRADE"
    return [{
        "date": date_str,
        "evaluated_at": ts,
        "outcome": outcome,
        "rationale": overview.get("why_summary", ""),
        "overview": overview,
        "trade_plan": None,
        "positions": get_positions_for_api(),
    }]
