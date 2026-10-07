# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.2: Portfolio guardrails layer — guidance only."""

from __future__ import annotations

import pytest

from app.core.portfolio.portfolio_guardrails import (
    MAX_SYMBOL_CONCENTRATION_PCT,
    MAX_SYMBOL_CRITICAL_PCT,
    TARGET_MAX_EXPOSURE_PCT,
    apply_guardrails,
)


def _snapshot(overrides=None, **kwargs):
    d = {
        "as_of": "2026-02-13T12:00:00",
        "total_open_positions": 0,
        "open_csp_count": 0,
        "open_cc_count": 0,
        "total_capital_committed": 0,
        "exposure_pct": None,
        "symbol_concentration": {"top_symbols": [], "max_symbol_pct": None},
        "cluster_risk_level": "UNKNOWN",
        "assignment_risk": {"status": "UNKNOWN", "positions_near_itm": None, "notional_itm_risk": None},
    }
    d.update(kwargs)
    if overrides:
        d.update(overrides)
    return d


def _candidate(symbol="SPY", mode="CSP", contracts=2, severity="READY"):
    return {
        "symbol": symbol,
        "type": mode,
        "mode_decision": mode,
        "suggested_contracts": contracts,
        "contracts_suggested": contracts,
        "severity": severity,
    }


def test_exposure_guardrail_reduces_size():
    """exposure_pct >= 35 → contracts halved."""
    snap = _snapshot(exposure_pct=40.0)
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 2
    assert "exposure_guardrail" in out["applied_rules"]
    assert any("Exposure high" in a for a in out["advisories"])


def test_exposure_critical_sets_zero():
    """exposure_pct >= 45 → contracts 0, severity ADVISORY."""
    snap = _snapshot(exposure_pct=50.0)
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 0
    assert out["severity_override"] == "ADVISORY"
    assert "exposure_critical" in out["applied_rules"]


def test_symbol_concentration_reduction():
    """max_symbol_pct >= 25 → contracts reduced 25%."""
    snap = _snapshot(
        symbol_concentration={"top_symbols": [{"symbol": "SPY", "committed": 40000, "pct_of_committed": 30}], "max_symbol_pct": 30}
    )
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 3  # 4 * 0.75 = 3
    assert "symbol_concentration" in out["applied_rules"]


def test_symbol_concentration_35_severity_advisory():
    """max_symbol_pct >= 35 → severity_override ADVISORY."""
    snap = _snapshot(
        symbol_concentration={"top_symbols": [{"symbol": "SPY", "committed": 50000, "pct_of_committed": 40}], "max_symbol_pct": 40}
    )
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["severity_override"] == "ADVISORY"
    assert "symbol_concentration_critical" in out["applied_rules"]


def test_cluster_high_reduction():
    """cluster_risk_level HIGH → contracts reduced 30%."""
    snap = _snapshot(cluster_risk_level="HIGH")
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 2  # 4 * 0.70 = 2.8 -> 2
    assert "cluster_risk" in out["applied_rules"]


def test_regime_down_reduction():
    """regime_state.mode DOWN → CSP contracts reduced 25%."""
    snap = _snapshot()
    cand = _candidate(mode="CSP", contracts=4)
    regime = {"mode": "DOWN"}
    out = apply_guardrails(snap, cand, regime_state=regime)
    assert out["adjusted_contracts"] == 3  # 4 * 0.75
    assert "regime_down" in out["applied_rules"]


def test_regime_down_cc_unchanged():
    """regime_state.mode DOWN does not reduce CC contracts."""
    snap = _snapshot()
    cand = _candidate(mode="CC", contracts=4)
    regime = {"mode": "DOWN"}
    out = apply_guardrails(snap, cand, regime_state=regime)
    assert out["adjusted_contracts"] == 4
    assert "regime_down" not in out["applied_rules"]


def test_regime_crash_zero():
    """regime_state.mode CRASH → contracts 0, severity ADVISORY."""
    snap = _snapshot()
    cand = _candidate(contracts=4)
    regime = {"mode": "CRASH"}
    out = apply_guardrails(snap, cand, regime_state=regime)
    assert out["adjusted_contracts"] == 0
    assert out["severity_override"] == "ADVISORY"
    assert "regime_crash" in out["applied_rules"]


def test_assignment_pressure_reduction():
    """positions_near_itm >= 3 → contracts reduced 40%."""
    snap = _snapshot(
        assignment_risk={"status": "ESTIMATED", "positions_near_itm": 4, "notional_itm_risk": 100000}
    )
    cand = _candidate(contracts=5)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 3  # 5 * 0.60 = 3
    assert "assignment_pressure" in out["applied_rules"]


def test_assignment_pressure_below_threshold():
    """positions_near_itm < 3 → no assignment pressure rule."""
    snap = _snapshot(
        assignment_risk={"status": "ESTIMATED", "positions_near_itm": 2, "notional_itm_risk": 50000}
    )
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 4
    assert "assignment_pressure" not in out["applied_rules"]


def test_multiple_rules_stack():
    """Multiple rules stack multiplicatively."""
    snap = _snapshot(
        exposure_pct=38.0,
        symbol_concentration={"max_symbol_pct": 30},
        cluster_risk_level="HIGH",
    )
    cand = _candidate(contracts=4)
    out = apply_guardrails(snap, cand)
    # 4 * 0.5 (exposure) = 2; 2 * 0.75 (symbol) = 1.5 -> 1; 1 * 0.70 (cluster) = 0.7 -> 0
    assert out["adjusted_contracts"] == 0
    assert len(out["applied_rules"]) >= 3


def test_never_negative_contracts():
    """adjusted_contracts never negative."""
    snap = _snapshot(exposure_pct=50.0, cluster_risk_level="HIGH")
    cand = _candidate(contracts=1)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] >= 0


def test_no_rules_applied_returns_original():
    """When no guardrails apply, returns original contracts."""
    snap = _snapshot(
        exposure_pct=20.0,
        symbol_concentration={"max_symbol_pct": 15},
        cluster_risk_level="LOW",
        assignment_risk={"positions_near_itm": 0},
    )
    cand = _candidate(contracts=3)
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 3
    assert out["severity_override"] is None
    assert len(out["applied_rules"]) == 0
    assert len(out["advisories"]) == 0


def test_candidate_contracts_suggested_alias():
    """Candidate can use contracts_suggested instead of suggested_contracts."""
    snap = _snapshot(exposure_pct=40.0)
    cand = {"symbol": "SPY", "mode_decision": "CSP", "contracts_suggested": 4}
    out = apply_guardrails(snap, cand)
    assert out["adjusted_contracts"] == 2
