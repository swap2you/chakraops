# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: Load view models from decision_latest.json + persistence for API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from app.core.settings import get_output_dir
except ImportError:
    def get_output_dir() -> str:
        return "out"


def _decision_latest_path() -> Path:
    return Path(get_output_dir()) / "decision_latest.json"


def load_decision_artifact() -> Optional[Dict[str, Any]]:
    """Load decision_latest.json. Returns None if missing or invalid."""
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
    """Build daily-overview dict from artifact (decision_snapshot, daily_trust_report, metadata)."""
    report = artifact.get("daily_trust_report") or {}
    meta = artifact.get("metadata") or {}
    snapshot = artifact.get("decision_snapshot") or {}
    stats = snapshot.get("stats") or {}
    why = snapshot.get("why_no_trade") or {}
    date_str = report.get("date") or meta.get("cycle_id") or ""
    if not date_str and meta.get("pipeline_timestamp"):
        date_str = str(meta["pipeline_timestamp"])[:10]
    links = {}
    if meta.get("pipeline_timestamp"):
        links["latest_decision_ts"] = meta["pipeline_timestamp"]
    return {
        "date": date_str,
        "run_mode": report.get("run_mode") or meta.get("run_mode") or "DRY_RUN",
        "config_frozen": report.get("config_frozen", False),
        "freeze_violation_changed_keys": report.get("freeze_violation_changed_keys") or [],
        "regime": meta.get("regime") or report.get("regime"),
        "regime_reason": meta.get("regime_reason") or report.get("regime_reason"),
        "symbols_evaluated": int(stats.get("symbols_evaluated") or report.get("trades_considered", 0) or 0),
        "selected_signals": len(snapshot.get("selected_signals") or []),
        "trades_ready": report.get("trades_ready", 0),
        "no_trade": report.get("trades_ready", 0) == 0,
        "why_summary": str(why.get("summary") or report.get("summary") or ""),
        "top_blockers": list(report.get("top_blocking_reasons") or []),
        "risk_posture": str(meta.get("risk_posture") or report.get("risk_posture") or "CONSERVATIVE"),
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
    """Build decision-history list (latest record from artifact + meta). Returns [] on error."""
    artifact = load_decision_artifact()
    if not artifact:
        return []
    meta = artifact.get("metadata") or {}
    report = artifact.get("daily_trust_report") or {}
    snapshot = artifact.get("decision_snapshot") or {}
    ts = meta.get("pipeline_timestamp") or ""
    date_str = ts[:10] if ts else report.get("date") or ""
    why = snapshot.get("why_no_trade") or {}
    rationale = str(why.get("summary") or report.get("summary") or "")
    outcome = "NO_TRADE" if report.get("trades_ready", 0) == 0 else "TRADE"
    return [{
        "date": date_str,
        "evaluated_at": ts,
        "outcome": outcome,
        "rationale": rationale,
        "overview": build_daily_overview_from_artifact(artifact) if artifact else None,
        "trade_plan": None,
        "positions": get_positions_for_api(),
    }]
