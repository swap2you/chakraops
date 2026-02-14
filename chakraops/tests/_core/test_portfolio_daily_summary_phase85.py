# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.5: Portfolio Daily Summary — DAILY Slack Portfolio Risk Summary."""

from __future__ import annotations

import pytest

from app.core.alerts.slack_dispatcher import _fmt_daily
from app.core.portfolio.portfolio_daily_summary import (
    TARGET_MAX_EXPOSURE_PCT,
    build_portfolio_daily_summary,
)


def _snapshot(exposure_pct=None, equity=None, open_csp=0, open_cc=0, max_symbol_pct=None, cluster_risk="UNKNOWN", warnings=None):
    d = {
        "exposure_pct": exposure_pct,
        "portfolio_equity_usd": equity,
        "equity_usd": equity,
        "open_csp_count": open_csp,
        "open_cc_count": open_cc,
        "symbol_concentration": {"max_symbol_pct": max_symbol_pct} if max_symbol_pct is not None else {},
        "cluster_risk_level": cluster_risk,
        "warnings": warnings or [],
    }
    return d


def _stress(scenarios=None, worst_case=None, warnings=None):
    return {
        "scenarios": scenarios or [],
        "worst_case": worst_case or {},
        "warnings": warnings or [],
    }


def test_daily_summary_formats_exposure_status_green_yellow_red():
    """Exposure: GREEN < 70% target, YELLOW 70–100%, RED >= target."""
    target = TARGET_MAX_EXPOSURE_PCT  # 35
    # GREEN: < 24.5 (70% of 35)
    snap_g = _snapshot(exposure_pct=20.0, equity=150_000)
    stress = _stress(worst_case={"shock_pct": -0.15, "estimated_unrealized_drawdown": 0.0, "survival_status": "OK"})
    out = build_portfolio_daily_summary(snap_g, stress)
    assert "GREEN" in out["lines"][1]
    # YELLOW: 70–100% of target (24.5–35)
    snap_y = _snapshot(exposure_pct=28.0, equity=150_000)
    out = build_portfolio_daily_summary(snap_y, stress)
    assert "YELLOW" in out["lines"][1]
    # RED: >= 35
    snap_r = _snapshot(exposure_pct=38.0, equity=150_000)
    out = build_portfolio_daily_summary(snap_r, stress)
    assert "RED" in out["lines"][1]


def test_daily_summary_includes_stress_minus_10_when_present():
    """Stress -10% scenario line when present."""
    snap = _snapshot(exposure_pct=22.4, equity=150_000, open_csp=3, open_cc=1)
    scenarios = [
        {"shock_pct": -0.10, "estimated_assignments": 2, "assignment_capital_required": 25_000,
         "estimated_unrealized_drawdown": 1_420, "post_shock_exposure_pct": 41.0, "survival_status": "TIGHT"},
        {"shock_pct": -0.15, "estimated_assignments": 3, "assignment_capital_required": 38_000,
         "estimated_unrealized_drawdown": 3_900, "post_shock_exposure_pct": 50.0, "survival_status": "CRITICAL"},
    ]
    worst = {"shock_pct": -0.15, "estimated_unrealized_drawdown": 3_900, "survival_status": "CRITICAL"}
    stress = _stress(scenarios=scenarios, worst_case=worst)
    out = build_portfolio_daily_summary(snap, stress)
    stress_lines = [ln for ln in out["lines"] if "Stress -10%" in ln]
    assert len(stress_lines) == 1
    assert "2 assigns" in stress_lines[0]
    assert "$25000" in stress_lines[0]
    assert "$1420" in stress_lines[0]
    assert "41.0%" in stress_lines[0]
    assert "TIGHT" in stress_lines[0]


def test_daily_summary_includes_worst_case():
    """Always include worst_case line."""
    snap = _snapshot(exposure_pct=22.0, equity=150_000)
    scenarios = [
        {"shock_pct": -0.15, "assignment_capital_required": 38_000,
         "estimated_unrealized_drawdown": 3_900, "survival_status": "CRITICAL"},
    ]
    worst = {"shock_pct": -0.15, "estimated_unrealized_drawdown": 3_900, "survival_status": "CRITICAL"}
    stress = _stress(scenarios=scenarios, worst_case=worst)
    out = build_portfolio_daily_summary(snap, stress)
    wc_lines = [ln for ln in out["lines"] if ln.startswith("Worst Case:")]
    assert len(wc_lines) == 1
    assert "-15%" in wc_lines[0]
    assert "$38000" in wc_lines[0]
    assert "$3900" in wc_lines[0]
    assert "CRITICAL" in wc_lines[0]


def test_daily_summary_handles_missing_equity():
    """Handle missing equity gracefully."""
    snap = _snapshot(exposure_pct=None, equity=None, open_csp=0, open_cc=0)
    stress = _stress(worst_case={"shock_pct": -0.15, "estimated_unrealized_drawdown": 0, "survival_status": "UNKNOWN"})
    out = build_portfolio_daily_summary(snap, stress)
    assert out["title"] == "Portfolio Risk Summary"
    assert "Equity: N/A" in out["lines"][0]
    assert "Exposure: N/A" in out["lines"][1]


def test_daily_summary_caps_warnings_to_two():
    """Show count; include up to first 2 warnings condensed."""
    snap = _snapshot(warnings=["missing sector for 2 positions", "low DTE on SPY"])
    stress = _stress(warnings=["another warning"])
    out = build_portfolio_daily_summary(snap, stress)
    warn_lines = [ln for ln in out["lines"] if ln.startswith("Warnings:")]
    assert len(warn_lines) == 1
    assert "3 " in warn_lines[0] or "3)" in warn_lines[0]
    assert "missing sector" in warn_lines[0]
    assert "low DTE" in warn_lines[0] or "another warning" in warn_lines[0]
    # At most 2 warnings condensed
    snap2 = _snapshot(warnings=["w1", "w2", "w3", "w4"])
    out2 = build_portfolio_daily_summary(snap2, _stress())
    wl2 = [ln for ln in out2["lines"] if ln.startswith("Warnings:")][0]
    assert "4 " in wl2 or "4)" in wl2
    assert "w1" in wl2
    assert "w2" in wl2
    assert "w3" not in wl2  # capped to 2


def test_daily_summary_handles_empty_positions():
    """Handle empty positions (no exposure, no stress scenarios with assignments)."""
    snap = _snapshot(exposure_pct=None, equity=150_000, open_csp=0, open_cc=0, max_symbol_pct=None, cluster_risk="UNKNOWN")
    scenarios = [
        {"shock_pct": -0.10, "estimated_assignments": 0, "assignment_capital_required": 0,
         "estimated_unrealized_drawdown": 0, "post_shock_exposure_pct": None, "survival_status": "OK"},
    ]
    worst = {"shock_pct": -0.15, "estimated_unrealized_drawdown": 0, "survival_status": "OK"}
    stress = _stress(scenarios=scenarios, worst_case=worst)
    out = build_portfolio_daily_summary(snap, stress)
    assert out["title"] == "Portfolio Risk Summary"
    assert "Open CSP: 0" in out["lines"][1]
    assert "Open CC: 0" in out["lines"][1]
    assert "Worst Case:" in " ".join(out["lines"])
    assert "Warnings: 0" in out["lines"]


def test_daily_payload_appends_portfolio_section():
    """DAILY _fmt_daily appends portfolio_risk_summary when present."""
    payload = {
        "top_signals": [],
        "open_positions_count": 2,
        "total_capital_used": 100_000,
        "exposure_pct": 25.0,
        "average_premium_capture": 0.75,
        "exit_alerts_today": 0,
        "portfolio_risk_summary": {
            "title": "Portfolio Risk Summary",
            "lines": [
                "Equity: $150,000 | Target Max Exposure: 35%",
                "Exposure: 22.4% (GREEN) | Open CSP: 3 | Open CC: 1",
            ],
        },
    }
    text = _fmt_daily(payload)
    assert "Portfolio Risk Summary" in text
    assert "Equity: $150,000" in text
    assert "Exposure: 22.4% (GREEN)" in text
    assert "DAILY SUMMARY" in text


def test_daily_payload_without_portfolio_section():
    """DAILY without portfolio_risk_summary omits the section."""
    payload = {
        "top_signals": [],
        "open_positions_count": 2,
        "exposure_pct": 25.0,
    }
    text = _fmt_daily(payload)
    assert "DAILY SUMMARY" in text
    assert "Portfolio Risk Summary" not in text
