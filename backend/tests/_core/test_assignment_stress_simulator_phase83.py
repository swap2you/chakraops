# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Assignment stress simulation — read-only risk modeling."""

from __future__ import annotations

import pytest

from app.core.portfolio.assignment_stress_simulator import (
    format_stress_summary,
    format_stress_summary_dynamic,
    simulate_assignment_stress,
    simulate_assignment_stress_dynamic,
)


def _pos(overrides=None, **kwargs):
    d = {
        "position_id": "test-uuid",
        "symbol": "SPY",
        "mode": "CSP",
        "strike": 500.0,
        "contracts": 1,
        "entry_spot": 498.0,
        "entry_premium": 10.0,
        "status": "OPEN",
    }
    d.update(kwargs)
    if overrides:
        d.update(overrides)
    return d


def _snapshot(total_committed=0, exposure_pct=None):
    d = {"total_capital_committed": total_committed}
    if exposure_pct is not None:
        d["exposure_pct"] = exposure_pct
    return d


def test_no_csp_returns_empty():
    """No CSP positions → empty scenarios list."""
    positions = [_pos(mode="CC", symbol="AAPL")]  # CC only
    snap = _snapshot(0)
    out = simulate_assignment_stress(snap, positions)
    assert out["scenarios"] == []
    assert out["worst_case"]["assignment_capital_required"] == 0.0
    assert out["worst_case"]["estimated_unrealized_drawdown"] == 0.0


def test_single_csp_assignment_triggered():
    """Single CSP with spot below strike after -5% shock → assignment."""
    # Spot 500, strike 500 → at the money. -5% shock: new_spot = 500 * 0.95 = 475. 475 <= 500 → assigned
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot(50000, 33.33)  # 50k committed, ~33% exposure
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    assert len(out["scenarios"]) == 1
    s = out["scenarios"][0]
    assert s["shock_pct"] == -0.05
    assert s["estimated_assignments"] == 1
    assert s["assignment_capital_required"] == 50_000  # 500 * 100 * 1
    assert s["estimated_unrealized_drawdown"] == 2500  # (500 - 475) * 100 * 1


def test_single_csp_not_triggered():
    """Single CSP with spot above strike after shock → no assignment."""
    # Spot 500, strike 450. -5% shock: new_spot = 475. 475 > 450 → not assigned
    positions = [_pos(entry_spot=500.0, strike=450.0, contracts=1)]
    snap = _snapshot(45000, 30)
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["estimated_assignments"] == 0
    assert s["assignment_capital_required"] == 0.0
    assert s["estimated_unrealized_drawdown"] == 0.0


def test_multiple_csp_aggregate():
    """Multiple CSPs aggregate assignments and capital."""
    positions = [
        _pos(entry_spot=500.0, strike=500.0, contracts=2),  # assigned at -5%
        _pos(entry_spot=400.0, strike=420.0, contracts=1),  # assigned at -5%: 400*0.95=380 <= 420
    ]
    snap = _snapshot(142000, 50)  # 2*50k + 1*42k = 142k
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["estimated_assignments"] == 3
    assert s["assignment_capital_required"] == 100_000 + 42_000  # 142k
    # Drawdown: (500-475)*100*2 + (420-380)*100*1 = 5000 + 4000 = 9000
    assert s["estimated_unrealized_drawdown"] == 9000


def test_drawdown_calculation_correct():
    """Drawdown = (strike - new_spot) * 100 * contracts for assigned positions."""
    # Spot 100, strike 100, contracts 1. -10% shock: new_spot = 90. loss = (100-90)*100 = 1000
    positions = [_pos(entry_spot=100.0, strike=100.0, contracts=1)]
    snap = _snapshot(10000)
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.10])
    s = out["scenarios"][0]
    assert s["estimated_unrealized_drawdown"] == 1000


def test_shock_levels_override():
    """Custom shock_levels override default."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot(50000)
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.02, -0.20])
    assert len(out["scenarios"]) == 2
    assert out["scenarios"][0]["shock_pct"] == -0.02
    assert out["scenarios"][1]["shock_pct"] == -0.20
    # -2%: new_spot 490 > 500? No, 490 <= 500, assigned
    # -20%: new_spot 400 <= 500, assigned
    assert out["scenarios"][0]["estimated_assignments"] == 1
    assert out["scenarios"][1]["estimated_assignments"] == 1
    assert out["scenarios"][1]["estimated_unrealized_drawdown"] > out["scenarios"][0]["estimated_unrealized_drawdown"]


def test_worst_case_selection():
    """worst_case is scenario with largest unrealized drawdown."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot(50000)
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05, -0.10, -0.15])
    wc = out["worst_case"]
    assert wc["shock_pct"] == -0.15
    assert wc["assignment_capital_required"] == 50_000
    assert wc["estimated_unrealized_drawdown"] == 7500  # (500 - 425) * 100


def test_missing_spot_skipped():
    """Positions without spot → skipped, warning added."""
    positions = [_pos(entry_spot=None, strike=500.0, contracts=1)]
    snap = _snapshot()
    out = simulate_assignment_stress(snap, positions)
    assert any("missing spot" in w.lower() for w in out["warnings"])
    assert len(out["scenarios"]) == 0 or all(s["estimated_assignments"] == 0 for s in out["scenarios"])


def test_missing_strike_skipped():
    """Positions without strike → skipped, warning added."""
    positions = [_pos(entry_spot=500.0, strike=None, contracts=1)]
    snap = _snapshot()
    out = simulate_assignment_stress(snap, positions)
    assert any("missing" in w.lower() for w in out["warnings"])


def test_post_shock_exposure_calculated():
    """post_shock_exposure_pct when portfolio_equity derivable from snapshot."""
    # existing_committed=50k, exposure_pct=33.33 → equity = 50k/0.3333 ≈ 150k
    # post-shock: existing 50k + assignment 50k = 100k. exposure = 100/150 ≈ 66.67%
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot(50_000, 33.33)
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["post_shock_exposure_pct"] is not None
    assert s["post_shock_exposure_pct"] > 33


def test_post_shock_exposure_none_when_equity_missing():
    """post_shock_exposure_pct None when exposure_pct missing in snapshot."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot(50_000)  # no exposure_pct
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["post_shock_exposure_pct"] is None


def test_drawdown_never_negative():
    """Drawdown clamped to >= 0."""
    # Edge: new_spot > strike (shouldn't assign, but defensive)
    positions = [_pos(entry_spot=600.0, strike=500.0, contracts=1)]
    snap = _snapshot()
    out = simulate_assignment_stress(snap, positions, shock_levels=[-0.05])
    for s in out["scenarios"]:
        assert s["estimated_unrealized_drawdown"] >= 0


def test_format_stress_summary():
    """format_stress_summary returns human-readable string."""
    result = {
        "scenarios": [
            {"shock_pct": -0.10, "estimated_assignments": 3, "assignment_capital_required": 45000, "estimated_unrealized_drawdown": 6200},
        ],
        "worst_case": {},
        "warnings": [],
    }
    s = format_stress_summary(result)
    assert "Stress -10%" in s
    assert "3 assignments" in s
    assert "45,000" in s or "45000" in s
    assert "6,200" in s or "6200" in s


def test_format_stress_summary_empty():
    """format_stress_summary returns message when no scenarios."""
    s = format_stress_summary({"scenarios": [], "worst_case": {}, "warnings": []})
    assert "No stress" in s


# --- Phase 8.3b: Dynamic stress + NAV shrink ---


def _snapshot_dynamic(portfolio_equity_usd=None, total_committed=0, exposure_pct=None):
    d = {"total_capital_committed": total_committed}
    if exposure_pct is not None:
        d["exposure_pct"] = exposure_pct
    if portfolio_equity_usd is not None:
        d["portfolio_equity_usd"] = portfolio_equity_usd
    return d


def test_dynamic_equity_missing_sets_unknown_and_none_fields():
    """When portfolio_equity_usd/equity_usd missing, shocked_equity/exposure/buffer None, survival UNKNOWN."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic()  # no equity
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["starting_equity"] is None
    assert s["shocked_equity"] is None
    assert s["post_shock_exposure_pct"] is None
    assert s["cash_buffer"] is None
    assert s["survival_status"] == "UNKNOWN"


def test_dynamic_shocked_equity_conservative():
    """CONSERVATIVE mode: shocked_equity = starting_equity - estimated_unrealized_drawdown."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["starting_equity"] == 100_000
    assert s["estimated_unrealized_drawdown"] == 2500  # (500-475)*100
    assert s["shocked_equity"] == 97_500


def test_dynamic_post_shock_exposure_uses_shocked_equity():
    """post_shock_exposure_pct uses shocked_equity as denominator."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    # post_shock_total_notional = csp_reserved (50k) + cc_shocked (0). shocked_equity = 97.5k
    # exposure = 100 * 50000 / 97500 ≈ 51.28
    assert s["post_shock_exposure_pct"] is not None
    assert s["post_shock_exposure_pct"] > 50
    assert s["post_shock_exposure_pct"] < 55


def test_dynamic_no_double_count_csp_reserved_cash():
    """CSP reserved cash is not additive on assignment — avoid double count."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["csp_reserved_cash"] == 50_000
    assert s["assignment_capital_required"] == 50_000
    assert s["total_notional_post_shock"] == 50_000  # csp_reserved only (no CC)


def test_dynamic_cc_notional_shocked_when_spot_present():
    """CC equity notional shocked when CC has spot."""
    cc_pos = _pos(symbol="AAPL", mode="CC", entry_spot=150.0, strike=155.0, contracts=1, shares=100)
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, [cc_pos], shock_levels=[-0.10])
    s = out["scenarios"][0]
    # CC notional shocked: 100 * (150 * 0.9) = 13500
    assert s["cc_equity_notional"] == 15_000  # pre-shock 100*150
    assert s["total_notional_post_shock"] == 13_500  # shocked CC + 0 csp


def test_dynamic_cash_buffer_and_survival_ok_tight_critical():
    """cash_buffer = equity - assignment_capital; survival OK/TIGHT/CRITICAL by buffer %."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05])
    s = out["scenarios"][0]
    assert s["cash_buffer"] == 50_000  # 100k - 50k
    assert s["survival_status"] == "OK"  # 50% >= 20%

    # TIGHT: buffer 10% of equity (100k - 90k = 10k)
    positions_heavy = [_pos(entry_spot=500.0, strike=500.0, contracts=18)]  # 900k required
    snap_heavy = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out_heavy = simulate_assignment_stress_dynamic(snap_heavy, positions_heavy, shock_levels=[-0.05])
    s_heavy = out_heavy["scenarios"][0]
    assert s_heavy["cash_buffer"] == 100_000 - 900_000  # negative
    assert s_heavy["survival_status"] == "CRITICAL"  # buffer < 5%


def test_dynamic_worst_case_selection():
    """worst_case = scenario with largest unrealized drawdown; tie-break most negative shock."""
    positions = [_pos(entry_spot=500.0, strike=500.0, contracts=1)]
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, positions, shock_levels=[-0.05, -0.10, -0.15])
    wc = out["worst_case"]
    assert wc["shock_pct"] == -0.15
    assert wc["estimated_unrealized_drawdown"] == 7500
    assert "survival_status" in wc
    assert "cash_buffer" in wc


def test_dynamic_notes_and_warnings_on_missing_fields():
    """Notes and warnings when CC missing spot or cost."""
    cc_no_spot = _pos(symbol="AAPL", mode="CC", entry_spot=None, strike=155.0, contracts=1, shares=100)
    snap = _snapshot_dynamic(portfolio_equity_usd=100_000)
    out = simulate_assignment_stress_dynamic(snap, [cc_no_spot], shock_levels=[-0.05])
    assert any("missing" in w.lower() for w in out["warnings"])
