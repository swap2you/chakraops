# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for rejection analytics and heatmap (Phase 5.2)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.observability.rejection_analytics import (
    STAGES,
    compute_rejection_heatmap,
    summarize_rejections,
)


def test_summarize_rejections_empty_snapshot():
    """Empty snapshot returns zero counts and empty tables."""
    summary = summarize_rejections({}, gate_result=None)
    assert summary["by_reason"] == {}
    assert set(summary["by_stage"].keys()) == set(STAGES)
    assert all(summary["by_stage"][s] == 0 for s in STAGES)
    assert summary["symbol_frequency"] == []
    assert summary["symbols_considered"] == 0
    assert summary["total_rejections"] == 0


def test_summarize_rejections_from_exclusions():
    """Exclusions in snapshot are counted by reason and stage."""
    snapshot = {
        "stats": {"symbols_evaluated": 50},
        "exclusions": [
            {"rule": "IV_RANK_LOW_SELL", "symbol": "AAPL", "stage": "SELECTION"},
            {"rule": "IV_RANK_LOW_SELL", "symbol": "MSFT", "stage": "SELECTION"},
            {"rule": "EARNINGS_WINDOW", "symbol": "GOOGL"},
        ],
    }
    summary = summarize_rejections(snapshot, gate_result=None)
    assert summary["by_reason"]["IV_RANK_LOW_SELL"] == 2
    assert summary["by_reason"]["EARNINGS_WINDOW"] == 1
    assert summary["by_stage"]["SELECTION"] >= 2
    assert summary["by_stage"]["ENVIRONMENT"] >= 1
    assert summary["symbols_considered"] == 50
    assert summary["total_rejections"] == 3
    # symbol_frequency: one row per (symbol, reason) pair
    assert len(summary["symbol_frequency"]) >= 3


def test_summarize_rejections_from_gate_result():
    """Gate result reasons are aggregated into by_reason and by_stage."""
    snapshot = {"stats": {"symbols_evaluated": 10}, "exclusions": []}
    gate = SimpleNamespace(allowed=False, reasons=["EARNINGS_WINDOW", "MACRO_EVENT_WINDOW", "EARNINGS_WINDOW"])
    summary = summarize_rejections(snapshot, gate_result=gate)
    assert summary["by_reason"]["EARNINGS_WINDOW"] == 2
    assert summary["by_reason"]["MACRO_EVENT_WINDOW"] == 1
    assert summary["by_stage"]["ENVIRONMENT"] >= 3
    assert summary["total_rejections"] == 3


def test_summarize_rejections_combined():
    """Snapshot exclusions and gate reasons are combined."""
    snapshot = {
        "exclusions": [{"rule": "NO_SELECTED_SIGNALS", "symbol": "UNKNOWN"}],
    }
    gate = SimpleNamespace(allowed=False, reasons=["EARNINGS_WINDOW"])
    summary = summarize_rejections(snapshot, gate_result=gate)
    assert summary["by_reason"].get("NO_SELECTED_SIGNALS") == 1
    assert summary["by_reason"].get("EARNINGS_WINDOW") == 1
    assert summary["total_rejections"] == 2


def test_compute_rejection_heatmap_empty():
    """Empty history returns empty heatmap structure."""
    heatmap = compute_rejection_heatmap([])
    assert heatmap["dates"] == []
    assert heatmap["reason_totals"] == {}
    assert heatmap["stage_totals"] != {}
    assert set(heatmap["stage_totals"].keys()) == set(STAGES)
    assert heatmap["matrix"] == []


def test_compute_rejection_heatmap_aggregates():
    """Heatmap aggregates by_reason and by_stage across history."""
    history = [
        {"date": "2026-01-01", "by_reason": {"EARNINGS_WINDOW": 5, "IV_RANK_LOW_SELL": 3}, "by_stage": {"ENVIRONMENT": 5, "SELECTION": 3}, "symbol_frequency": [{"symbol": "AAPL", "reason": "EARNINGS_WINDOW", "count": 2}]},
        {"date": "2026-01-02", "by_reason": {"EARNINGS_WINDOW": 2, "MACRO_EVENT_WINDOW": 1}, "by_stage": {"ENVIRONMENT": 3}, "symbol_frequency": []},
    ]
    heatmap = compute_rejection_heatmap(history)
    assert heatmap["dates"] == ["2026-01-01", "2026-01-02"]
    assert heatmap["reason_totals"]["EARNINGS_WINDOW"] == 7
    assert heatmap["reason_totals"]["IV_RANK_LOW_SELL"] == 3
    assert heatmap["reason_totals"]["MACRO_EVENT_WINDOW"] == 1
    assert heatmap["stage_totals"]["ENVIRONMENT"] == 8
    assert heatmap["stage_totals"]["SELECTION"] == 3
    assert len(heatmap["matrix"]) == 2
    assert heatmap["symbol_totals"].get("AAPL") == 2
