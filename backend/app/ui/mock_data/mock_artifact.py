# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock full decision artifact for UI_MODE=MOCK (Phase 6.6)."""

from datetime import datetime, timezone
from typing import Any, Dict

from app.ui.mock_data.mock_daily_overview import mock_daily_overview_no_trade


def get_mock_artifact() -> Dict[str, Any]:
    """Return a minimal decision artifact dict so dashboard renders without DB or pipeline.
    Uses DailyOverviewView-based trust report shape.
    """
    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    daily = mock_daily_overview_no_trade(date_str)
    daily_dict = daily.to_dict()
    return {
        "decision_snapshot": {
            "stats": {
                "symbols_evaluated": daily_dict.get("symbols_evaluated", 50),
                "total_candidates": 45,
                "selected_count": 0,
            },
            "candidates": [],
            "scored_candidates": [],
            "selected_signals": [],
            "exclusions": [],
            "exclusion_summary": {},
            "symbols_with_options": [],
            "symbols_without_options": {},
            "data_source": "mock",
            "as_of": ts,
            "pipeline_timestamp": ts,
            "trade_proposal": None,
            "why_no_trade": {"summary": daily_dict.get("why_summary", "No READY trade; capital protected.")},
        },
        "execution_gate": {"allowed": False, "reasons": ["Mock mode — no live data"]},
        "execution_plan": {"allowed": False, "blocked_reason": "Mock mode", "orders": []},
        "dry_run_result": {"allowed": False},
        "regime": "NEUTRAL",
        "regime_reason": "Mock",
        "daily_trust_report": {
            "report_type": "daily",
            "as_of": ts,
            "date": date_str,
            "trades_considered": daily_dict.get("symbols_evaluated", 50),
            "trades_rejected": 45,
            "trades_ready": 0,
            "capital_protected_estimate": 0.0,
            "top_blocking_reasons": daily_dict.get("top_blockers", []),
            "summary": daily_dict.get("why_summary", "No trades today — capital protected."),
            "run_mode": daily_dict.get("run_mode", "DRY_RUN"),
            "config_frozen": daily_dict.get("config_frozen", True),
            "freeze_violation_changed_keys": daily_dict.get("freeze_violation_changed_keys", []),
        },
        "metadata": {
            "data_source": "mock",
            "pipeline_timestamp": ts,
            "risk_posture": daily_dict.get("risk_posture", "CONSERVATIVE"),
            "run_mode": daily_dict.get("run_mode", "DRY_RUN"),
            "config_frozen": daily_dict.get("config_frozen", True),
        },
    }
