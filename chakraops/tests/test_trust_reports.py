# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for daily and weekly trust reports (Phase 5.3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.observability.trust_reports import (
    generate_daily_report,
    generate_weekly_report,
    report_to_markdown,
)


def _make_snapshot(
    symbols_evaluated: int = 50,
    total_candidates: int = 100,
    exclusions: list | None = None,
) -> dict:
    """Minimal decision snapshot dict for tests."""
    return {
        "stats": {
            "symbols_evaluated": symbols_evaluated,
            "total_candidates": total_candidates,
        },
        "exclusions": exclusions or [],
        "selected_signals": [],
    }


def test_generate_daily_report_empty_snapshot():
    """Empty snapshot produces report with zero counts."""
    report = generate_daily_report({}, gate_result=None, trade_proposal=None)
    assert report["report_type"] == "daily"
    assert report["trades_considered"] == 0
    assert report["trades_rejected"] == 0
    assert report["trades_ready"] == 0
    assert report["capital_protected_estimate"] == 0.0
    assert report["top_blocking_reasons"] == []
    assert "summary" in report
    assert "as_of" in report


def test_generate_daily_report_uses_stats():
    """Daily report uses stats.symbols_evaluated or total_candidates."""
    snapshot = _make_snapshot(symbols_evaluated=47, total_candidates=80)
    report = generate_daily_report(snapshot, gate_result=None, trade_proposal=None)
    assert report["trades_considered"] == 47


def test_generate_daily_report_trades_rejected_from_exclusions():
    """Rejections come from summarize_rejections (exclusions + gate)."""
    snapshot = _make_snapshot(
        symbols_evaluated=50,
        exclusions=[
            {"rule": "IV_RANK_LOW_SELL", "symbol": "AAPL"},
            {"rule": "EARNINGS_WINDOW", "symbol": "MSFT"},
        ],
    )
    gate = SimpleNamespace(allowed=False, reasons=["EARNINGS_WINDOW"])
    report = generate_daily_report(snapshot, gate_result=gate, trade_proposal=None)
    assert report["trades_rejected"] == 3  # 2 exclusions + 1 gate
    assert len(report["top_blocking_reasons"]) >= 1
    codes = [r["code"] for r in report["top_blocking_reasons"]]
    assert "EARNINGS_WINDOW" in codes


def test_generate_daily_report_trades_ready_when_proposal_ready():
    """When trade_proposal is READY, trades_ready is 1."""
    snapshot = _make_snapshot(symbols_evaluated=50)
    proposal = SimpleNamespace(execution_status="READY", max_loss=500.0)
    report = generate_daily_report(snapshot, gate_result=None, trade_proposal=proposal)
    assert report["trades_ready"] == 1
    assert report["capital_protected_estimate"] == 0.0  # READY => no capital protected


def test_generate_daily_report_capital_protected_when_blocked():
    """When no READY and proposal has max_loss, capital_protected_estimate is set."""
    snapshot = _make_snapshot(symbols_evaluated=50)
    proposal = SimpleNamespace(execution_status="BLOCKED", max_loss=1200.50)
    report = generate_daily_report(
        snapshot, gate_result=None, trade_proposal=proposal, as_of="2026-01-31T12:00:00Z"
    )
    assert report["trades_ready"] == 0
    assert report["capital_protected_estimate"] == 1200.50
    assert report["as_of"] == "2026-01-31T12:00:00Z"


def test_generate_daily_report_capital_protected_from_dict_proposal():
    """Capital protected is read from dict trade_proposal.max_loss."""
    snapshot = _make_snapshot(symbols_evaluated=50)
    proposal = {"execution_status": "BLOCKED", "max_loss": 800.0}
    report = generate_daily_report(snapshot, gate_result=None, trade_proposal=proposal)
    assert report["capital_protected_estimate"] == 800.0


def test_generate_daily_report_top_blocking_reasons_capped():
    """Top blocking reasons are at most 5."""
    snapshot = _make_snapshot(
        exclusions=[
            {"rule": f"R{i}", "symbol": "X"} for i in range(10)
        ],
    )
    report = generate_daily_report(snapshot, gate_result=None, trade_proposal=None)
    assert len(report["top_blocking_reasons"]) <= 5


def test_generate_weekly_report_empty_history():
    """Empty history produces weekly report with zeros."""
    report = generate_weekly_report([], as_of="2026-01-31")
    assert report["report_type"] == "weekly"
    assert report["as_of"] == "2026-01-31"
    assert report["period_days"] == 0
    assert report["trades_considered"] == 0
    assert report["trades_rejected"] == 0
    assert report["trades_ready"] == 0
    assert report["capital_protected_estimate"] == 0.0
    assert report["top_blocking_reasons"] == []
    assert "Weekly:" in report["summary"]


def test_generate_weekly_report_aggregates_daily():
    """Weekly report aggregates trades_considered, rejected, ready, capital."""
    history = [
        {
            "trades_considered": 50,
            "trades_rejected": 10,
            "trades_ready": 0,
            "capital_protected_estimate": 500.0,
            "top_blocking_reasons": [{"code": "EARNINGS_WINDOW", "count": 5}],
        },
        {
            "trades_considered": 48,
            "trades_rejected": 8,
            "trades_ready": 1,
            "capital_protected_estimate": 0.0,
            "top_blocking_reasons": [{"code": "EARNINGS_WINDOW", "count": 3}, {"code": "IV_RANK_LOW", "count": 2}],
        },
    ]
    report = generate_weekly_report(history, as_of="2026-02-01")
    assert report["period_days"] == 2
    assert report["trades_considered"] == 98
    assert report["trades_rejected"] == 18
    assert report["trades_ready"] == 1
    assert report["capital_protected_estimate"] == 500.0
    codes = [r["code"] for r in report["top_blocking_reasons"]]
    assert "EARNINGS_WINDOW" in codes
    assert report["top_blocking_reasons"][0]["code"] == "EARNINGS_WINDOW"
    assert report["top_blocking_reasons"][0]["count"] == 8


def test_generate_weekly_report_accepts_by_reason():
    """Weekly report can aggregate from records with by_reason dict."""
    history = [
        {"trades_considered": 10, "trades_rejected": 2, "by_reason": {"A": 1, "B": 1}},
        {"trades_considered": 10, "trades_rejected": 3, "by_reason": {"A": 2, "C": 1}},
    ]
    report = generate_weekly_report(history)
    assert report["trades_considered"] == 20
    assert report["trades_rejected"] == 5
    reason_codes = [r["code"] for r in report["top_blocking_reasons"]]
    assert "A" in reason_codes
    assert "B" in reason_codes
    assert "C" in reason_codes


def test_report_to_markdown_daily():
    """Markdown export includes title, summary, metrics, top blocking reasons."""
    report = {
        "report_type": "daily",
        "as_of": "2026-01-31T12:00:00Z",
        "summary": "No trades met safety criteria.",
        "trades_considered": 50,
        "trades_rejected": 12,
        "trades_ready": 0,
        "capital_protected_estimate": 1000.0,
        "top_blocking_reasons": [
            {"code": "EARNINGS_WINDOW", "count": 5},
            {"code": "IV_RANK_LOW_SELL", "count": 3},
        ],
    }
    md = report_to_markdown(report)
    assert "# Trust Report (Daily)" in md
    assert "**As of:** 2026-01-31T12:00:00Z" in md
    assert "## Summary" in md
    assert "No trades met safety criteria." in md
    assert "## Metrics" in md
    assert "**Trades considered:** 50" in md
    assert "**Trades rejected:** 12" in md
    assert "**Trades READY:** 0" in md
    assert "**Capital protected estimate:** $1,000.00" in md
    assert "## Top blocking reasons" in md
    assert "EARNINGS_WINDOW: 5" in md
    assert "IV_RANK_LOW_SELL: 3" in md


def test_report_to_markdown_weekly():
    """Markdown export for weekly includes period_days in metrics if present."""
    report = {
        "report_type": "weekly",
        "as_of": "2026-02-01",
        "period_days": 5,
        "summary": "Weekly: 200 considered, 40 rejected, 1 READY.",
        "trades_considered": 200,
        "trades_rejected": 40,
        "trades_ready": 1,
        "capital_protected_estimate": 2500.0,
        "top_blocking_reasons": [{"code": "EARNINGS_WINDOW", "count": 20}],
    }
    md = report_to_markdown(report)
    assert "# Trust Report (Weekly)" in md
    assert "**Trades considered:** 200" in md
    assert "EARNINGS_WINDOW: 20" in md


def test_report_to_markdown_empty_reasons():
    """Markdown with no top_blocking_reasons still renders."""
    report = {
        "report_type": "daily",
        "as_of": "",
        "summary": "Ok.",
        "trades_considered": 0,
        "trades_rejected": 0,
        "trades_ready": 0,
        "capital_protected_estimate": 0,
        "top_blocking_reasons": [],
    }
    md = report_to_markdown(report)
    assert "# Trust Report (Daily)" in md
    assert "## Top blocking reasons" in md


def test_generate_daily_report_run_mode_and_config_frozen():
    """Phase 6.1: daily report includes run_mode and config_frozen when provided."""
    snapshot = _make_snapshot(symbols_evaluated=10)
    report = generate_daily_report(
        snapshot, gate_result=None, trade_proposal=None,
        run_mode="PAPER_LIVE", config_frozen=True,
    )
    assert report["run_mode"] == "PAPER_LIVE"
    assert report["config_frozen"] is True
    report2 = generate_daily_report(
        snapshot, gate_result=None, trade_proposal=None,
        run_mode="LIVE", config_frozen=False, freeze_violation_changed_keys=["volatility", "portfolio"],
    )
    assert report2["run_mode"] == "LIVE"
    assert report2["config_frozen"] is False
    assert report2["freeze_violation_changed_keys"] == ["volatility", "portfolio"]


def test_report_to_markdown_run_and_freeze():
    """Phase 6.1: Markdown export includes Run & freeze section when run_mode/config_frozen present."""
    report = {
        "report_type": "daily",
        "as_of": "2026-01-31T12:00:00Z",
        "summary": "Ok.",
        "trades_considered": 50,
        "trades_rejected": 5,
        "trades_ready": 0,
        "capital_protected_estimate": 0,
        "top_blocking_reasons": [],
        "run_mode": "LIVE",
        "config_frozen": True,
    }
    md = report_to_markdown(report)
    assert "## Run & freeze" in md or "Run & freeze" in md
    assert "LIVE" in md
    assert "YES" in md
    report["config_frozen"] = False
    report["freeze_violation_changed_keys"] = ["volatility", "confidence"]
    md2 = report_to_markdown(report)
    assert "NO" in md2
    assert "volatility" in md2 and "confidence" in md2
