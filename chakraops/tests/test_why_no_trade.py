# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for why-no-trade explanation engine (Phase 5.1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.observability.why_no_trade import explain_no_trade
from app.execution.execution_gate import ExecutionGateResult


def _make_snapshot(
    symbols_evaluated: int = 47,
    selected_count: int = 0,
    exclusions: list | None = None,
) -> dict:
    """Minimal decision snapshot dict for tests."""
    return {
        "stats": {"symbols_evaluated": symbols_evaluated, "total_candidates": 100},
        "selected_signals": [{}] * selected_count if selected_count else [],
        "exclusions": exclusions or [],
    }


def test_no_ready_trades_explanation_present():
    """When no READY trade, explanation has no_trade=true and summary."""
    snapshot = _make_snapshot(symbols_evaluated=47, selected_count=6)
    gate = ExecutionGateResult(allowed=False, reasons=["EARNINGS_WINDOW", "NO_SELECTED_SIGNALS"])
    result = explain_no_trade(snapshot, gate_result=gate, trade_proposal=None)
    assert result["no_trade"] is True
    assert "summary" in result
    assert "No trades met safety criteria" in result["summary"]
    assert result["symbols_considered"] == 47
    assert result["symbols_passed_selection"] == 6
    assert result["symbols_ready"] == 0


def test_ready_trade_exists_no_explanation_attached():
    """When a trade is READY, no_trade=false; caller attaches block only when no_trade true."""
    snapshot = _make_snapshot(symbols_evaluated=50, selected_count=1)
    gate = ExecutionGateResult(allowed=True, reasons=[])
    proposal = SimpleNamespace(execution_status="READY")
    result = explain_no_trade(snapshot, gate_result=gate, trade_proposal=proposal)
    assert result["no_trade"] is False
    assert result["symbols_ready"] == 1
    assert "At least one trade is READY" in result["summary"]


def test_ready_trade_dict_execution_status():
    """When trade_proposal is a dict with execution_status READY, no_trade=false."""
    snapshot = _make_snapshot(symbols_evaluated=50, selected_count=1)
    proposal_dict = {"execution_status": "READY"}
    result = explain_no_trade(snapshot, gate_result=None, trade_proposal=proposal_dict)
    assert result["no_trade"] is False
    assert result["symbols_ready"] == 1


def test_blocked_trade_no_ready():
    """When trade_proposal has execution_status BLOCKED, no_trade=true."""
    snapshot = _make_snapshot(symbols_evaluated=50, selected_count=1)
    proposal = SimpleNamespace(execution_status="BLOCKED")
    result = explain_no_trade(snapshot, gate_result=None, trade_proposal=proposal)
    assert result["no_trade"] is True
    assert result["symbols_ready"] == 0


def test_aggregation_counts():
    """Exclusion and gate reasons are aggregated by code; top 3 = primary_reasons."""
    snapshot = _make_snapshot(
        symbols_evaluated=47,
        selected_count=0,
        exclusions=[
            {"rule": "VOLATILITY_SPIKE", "symbol": "AAPL"},
            {"rule": "VOLATILITY_SPIKE", "symbol": "MSFT"},
            {"rule": "EARNINGS_WINDOW", "symbol": "GOOGL"},
        ]
        + [{"rule": "VOLATILITY_SPIKE"}] * 10
        + [{"rule": "EARNINGS_WINDOW"}] * 7,
    )
    gate = ExecutionGateResult(
        allowed=False,
        reasons=["EARNINGS_WINDOW", "MACRO_EVENT_WINDOW", "EARNINGS_WINDOW"],
    )
    result = explain_no_trade(snapshot, gate_result=gate, trade_proposal=None)
    assert result["no_trade"] is True
    # VOLATILITY_SPIKE: 12, EARNINGS_WINDOW: 8+2=10 (from exclusions + gate), MACRO_EVENT_WINDOW: 1
    primary = result["primary_reasons"]
    secondary = result["secondary_reasons"]
    codes_seen = {p["code"]: p["count"] for p in primary} | {s["code"]: s["count"] for s in secondary}
    assert "VOLATILITY_SPIKE" in codes_seen
    assert codes_seen["VOLATILITY_SPIKE"] == 12
    assert "EARNINGS_WINDOW" in codes_seen
    assert codes_seen["EARNINGS_WINDOW"] == 10
    assert len(primary) <= 3
    assert len(primary) + len(secondary) >= 1


def test_primary_reasons_top_3():
    """Primary reasons are at most top 3 by count."""
    snapshot = _make_snapshot(
        exclusions=[
            {"rule": "A"},
            {"rule": "A"},
            {"rule": "A"},
            {"rule": "B"},
            {"rule": "B"},
            {"rule": "C"},
        ],
    )
    result = explain_no_trade(snapshot, gate_result=None, trade_proposal=None)
    primary = result["primary_reasons"]
    assert len(primary) == 3
    assert primary[0]["code"] == "A" and primary[0]["count"] == 3
    assert primary[1]["code"] == "B" and primary[1]["count"] == 2
    assert primary[2]["code"] == "C" and primary[2]["count"] == 1
    assert result["secondary_reasons"] == []


def test_empty_snapshot():
    """Snapshot with no stats/exclusions still returns valid structure."""
    result = explain_no_trade({}, gate_result=None, trade_proposal=None)
    assert result["no_trade"] is True
    assert result["symbols_considered"] == 0
    assert result["symbols_passed_selection"] == 0
    assert result["symbols_ready"] == 0
    assert result["primary_reasons"] == []
    assert result["secondary_reasons"] == []
    assert "summary" in result
