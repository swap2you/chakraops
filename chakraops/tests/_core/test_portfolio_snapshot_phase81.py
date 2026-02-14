# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.1: Portfolio snapshot engine — calculation only."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.portfolio.portfolio_snapshot import build_portfolio_snapshot, load_open_positions


def _pos(overrides=None, **kwargs):
    d = {
        "position_id": "test-uuid",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_date": (date.today() - timedelta(days=10)).isoformat(),
        "expiration": (date.today() + timedelta(days=35)).isoformat(),
        "strike": 500.0,
        "contracts": 1,
        "entry_premium": 10.0,
        "entry_spot": 498.0,
        "notes": "",
        "status": "OPEN",
    }
    d.update(kwargs)
    if overrides:
        d.update(overrides)
    return d


def test_snapshot_empty_ledger_returns_zeros_and_none():
    """Empty positions list → zeros and None where appropriate."""
    snap = build_portfolio_snapshot([], None)
    assert snap["total_open_positions"] == 0
    assert snap["open_csp_count"] == 0
    assert snap["open_cc_count"] == 0
    assert snap["total_capital_committed"] == 0.0
    assert snap["exposure_pct"] is None
    assert snap["avg_premium_capture"] is None
    assert snap["weighted_dte"] is None
    assert snap["assignment_risk"]["status"] == "UNKNOWN"
    assert snap["symbol_concentration"]["top_symbols"] == []
    assert snap["symbol_concentration"]["max_symbol_pct"] is None
    assert snap["sector_breakdown"]["status"] == "UNKNOWN"
    assert snap["cluster_risk_level"] == "UNKNOWN"
    assert "cluster_breakdown" in snap
    assert snap["cluster_breakdown"]["status"] == "UNKNOWN"
    assert snap["cluster_breakdown"]["by_cluster"] == []
    assert snap["max_cluster_pct"] is None
    assert snap["regime_adjusted_exposure"] is None
    assert isinstance(snap["warnings"], list)


def test_snapshot_csp_only_committed_and_exposure():
    """CSP positions → committed = strike * 100 * contracts; exposure_pct when equity provided."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=2),
        _pos(symbol="QQQ", strike=400.0, contracts=1),
    ]
    equity = 200_000.0
    snap = build_portfolio_snapshot(positions, equity)
    assert snap["total_open_positions"] == 2
    assert snap["open_csp_count"] == 2
    assert snap["open_cc_count"] == 0
    # SPY: 500*100*2 = 100000, QQQ: 400*100*1 = 40000 → 140000
    assert snap["total_capital_committed"] == 140_000.0
    assert snap["exposure_pct"] == pytest.approx(70.0)
    # Phase 8.6: SPY+QQQ map to INDEX_ETF → 2 in cluster → MEDIUM
    assert snap["cluster_risk_level"] == "MEDIUM"
    assert snap["sector_breakdown"]["status"] == "OK"  # mapped to ETF


def test_snapshot_mixed_csp_cc_no_fake_holdings():
    """Mixed CSP/CC: CSP committed from strike; CC missing cost (no entry_spot/cost_basis) yields warning and committed=0."""
    csp = _pos(symbol="SPY", mode="CSP", strike=500.0, contracts=1)
    cc_missing_cost = _pos(
        symbol="AAPL",
        mode="CC",
        strike=150.0,
        contracts=1,
        entry_spot=None,
        # no cost_basis_per_share → committed=0 + warning
    )
    positions = [csp, cc_missing_cost]
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["total_open_positions"] == 2
    assert snap["open_csp_count"] == 1
    assert snap["open_cc_count"] == 1
    # CSP: 500*100*1 = 50000
    # CC: missing cost → 0 + warning
    assert snap["total_capital_committed"] == 50_000.0
    assert any("CC" in w and "committed=0" in w for w in snap["warnings"])


def test_snapshot_cc_with_shares_and_cost():
    """CC with shares and entry_spot → committed = shares * entry_spot."""
    cc = _pos(
        symbol="AAPL",
        mode="CC",
        strike=150.0,
        contracts=1,
        entry_spot=148.0,
        shares=100,
    )
    positions = [cc]
    snap = build_portfolio_snapshot(positions, 20_000.0)
    assert snap["open_cc_count"] == 1
    assert snap["total_capital_committed"] == 14_800.0  # 100 * 148
    assert snap["exposure_pct"] == pytest.approx(74.0)


def test_snapshot_weighted_dte_weighting_by_committed():
    """weighted_dte is DTE weighted by committed capital. Use explicit dte for determinism."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=2, dte=10),  # DTE 10, committed 100k
        _pos(symbol="QQQ", strike=400.0, contracts=1, dte=40),  # DTE 40, committed 40k
    ]
    snap = build_portfolio_snapshot(positions, 200_000.0)
    assert snap["weighted_dte"] is not None
    # 10 * 100000 + 40 * 40000 = 1000000 + 1600000 = 2600000 / 140000 ≈ 18.57
    expected_wdte = (10 * 100_000 + 40 * 40_000) / 140_000
    assert snap["weighted_dte"] == pytest.approx(expected_wdte)


def test_snapshot_weighted_dte_expiry_based_stable_with_fixed_as_of():
    """Expiry-based DTE is stable with fixed as_of UTC."""
    # Fixed as_of near midnight UTC
    as_of = datetime(2026, 2, 13, 23, 59, 0, tzinfo=timezone.utc)
    exp_short = "2026-02-23"  # 10 days from as_of date
    exp_long = "2026-03-25"   # 40 days from as_of date
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=2, expiration=exp_short),
        _pos(symbol="QQQ", strike=400.0, contracts=1, expiration=exp_long),
    ]
    snap = build_portfolio_snapshot(positions, 200_000.0, as_of=as_of)
    assert snap["weighted_dte"] is not None
    # (2026-02-23 - 2026-02-13).days = 10, (2026-03-25 - 2026-02-13).days = 40
    expected_wdte = (10 * 100_000 + 40 * 40_000) / 140_000
    assert snap["weighted_dte"] == pytest.approx(expected_wdte)


def test_snapshot_symbol_concentration_top_symbols():
    """symbol_concentration: top symbols by committed, max_symbol_pct."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=2),   # 100k
        _pos(symbol="QQQ", strike=400.0, contracts=1),   # 40k
        _pos(symbol="SPY", strike=510.0, contracts=1),   # 51k → SPY total 151k
    ]
    snap = build_portfolio_snapshot(positions, 500_000.0)
    top = snap["symbol_concentration"]["top_symbols"]
    assert len(top) <= 5
    # SPY 151k, QQQ 40k; total 191k. SPY pct ≈ 79.06
    spy_entry = next((t for t in top if t["symbol"] == "SPY"), None)
    assert spy_entry is not None
    assert spy_entry["committed"] == 151_000.0
    assert snap["symbol_concentration"]["max_symbol_pct"] is not None
    assert snap["symbol_concentration"]["max_symbol_pct"] == pytest.approx(100.0 * 151_000 / 191_000, rel=0.01)


def test_snapshot_assignment_risk_unknown_when_missing_spot_strike():
    """assignment_risk UNKNOWN when no CSP has spot+strike."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=1, entry_spot=None),  # no spot
    ]
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["assignment_risk"]["status"] == "UNKNOWN"
    assert snap["assignment_risk"]["notional_itm_risk"] is None
    assert snap["assignment_risk"]["positions_near_itm"] is None


def test_snapshot_assignment_risk_estimated_when_spot_strike_present():
    """assignment_risk ESTIMATED when CSP has spot+strike; positions_near_itm counts spot <= strike*1.02."""
    # Near ITM: spot 510, strike 500 → 510 <= 510? 500*1.02=510, so 510<=510 yes
    pos_near = _pos(symbol="SPY", strike=500.0, contracts=1, entry_spot=510.0)
    # OTM: spot 480, strike 500 → 480 <= 510 yes (still within 2%)
    # Actually 480 <= 500*1.02 = 510, so yes, 480 is "near" - within 2% above strike
    # Spec: spot <= strike * 1.02 (within 2% of ITM/ATM)
    pos_otm = _pos(symbol="QQQ", strike=400.0, contracts=1, entry_spot=380.0)  # 380 <= 408, near
    positions = [pos_near, pos_otm]
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["assignment_risk"]["status"] == "ESTIMATED"
    assert snap["assignment_risk"]["positions_near_itm"] == 2
    assert snap["assignment_risk"]["notional_itm_risk"] == 50_000.0 + 40_000.0


def test_snapshot_assignment_risk_near_itm_threshold():
    """Spot > strike*1.02 → not near ITM."""
    # strike 500, 1.02*500=510. Spot 511 is OTM, not near
    pos = _pos(symbol="SPY", strike=500.0, contracts=1, entry_spot=511.0)
    snap = build_portfolio_snapshot([pos], 100_000.0)
    assert snap["assignment_risk"]["status"] == "ESTIMATED"
    assert snap["assignment_risk"]["positions_near_itm"] == 0
    assert snap["assignment_risk"]["notional_itm_risk"] == 0.0


def test_snapshot_cluster_risk_unknown_when_missing_cluster_field():
    """cluster_risk_level UNKNOWN when symbol not in cluster map (unmapped)."""
    positions = [_pos(symbol="XYZ", strike=500.0, contracts=1)]  # XYZ not in DEFAULT_CLUSTER_MAP
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["cluster_risk_level"] == "UNKNOWN"


def test_snapshot_cluster_risk_high_medium_low():
    """cluster_risk_level: >=3 HIGH, ==2 MEDIUM, ==1 LOW."""
    # 3 positions in same cluster → HIGH
    positions_high = [
        _pos(symbol="SPY", strike=500.0, contracts=1, cluster="tech"),
        _pos(symbol="QQQ", strike=400.0, contracts=1, cluster="tech"),
        _pos(symbol="AAPL", strike=150.0, contracts=1, cluster="tech", mode="CC", shares=100, entry_spot=148.0),
    ]
    snap = build_portfolio_snapshot(positions_high, 100_000.0)
    assert snap["cluster_risk_level"] == "HIGH"

    # 2 in cluster → MEDIUM
    positions_med = [
        _pos(symbol="SPY", strike=500.0, contracts=1, cluster="tech"),
        _pos(symbol="QQQ", strike=400.0, contracts=1, cluster="tech"),
    ]
    snap2 = build_portfolio_snapshot(positions_med, 100_000.0)
    assert snap2["cluster_risk_level"] == "MEDIUM"

    # 1 in cluster → LOW
    positions_low = [_pos(symbol="SPY", strike=500.0, contracts=1, cluster="tech")]
    snap3 = build_portfolio_snapshot(positions_low, 100_000.0)
    assert snap3["cluster_risk_level"] == "LOW"


def test_snapshot_sector_breakdown_when_present():
    """sector_breakdown OK when positions have sector field."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=1, sector="tech"),
        _pos(symbol="QQQ", strike=400.0, contracts=1, sector="tech"),
    ]
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["sector_breakdown"]["status"] == "OK"
    assert len(snap["sector_breakdown"]["by_sector"]) >= 1
    tech = next((s for s in snap["sector_breakdown"]["by_sector"] if s["sector"] == "tech"), None)
    assert tech is not None
    assert tech["committed"] == 90_000.0


def test_snapshot_regime_adjusted_exposure():
    """regime_adjusted_exposure = exposure_pct * throttle_factor when regime_state provided."""
    positions = [_pos(symbol="SPY", strike=500.0, contracts=2)]
    equity = 200_000.0
    regime = {"throttle_factor": 0.8}
    snap = build_portfolio_snapshot(positions, equity, regime_state=regime)
    assert snap["exposure_pct"] == pytest.approx(50.0)  # 100k/200k
    assert snap["regime_adjusted_exposure"] == pytest.approx(40.0)  # 50 * 0.8


def test_snapshot_avg_premium_capture_from_positions():
    """avg_premium_capture from position.premium_capture_pct when present."""
    positions = [
        _pos(symbol="SPY", strike=500.0, contracts=1, premium_capture_pct=0.50),
        _pos(symbol="QQQ", strike=400.0, contracts=1, premium_capture_pct=0.70),
    ]
    snap = build_portfolio_snapshot(positions, 100_000.0)
    assert snap["avg_premium_capture"] == pytest.approx(0.60)


def test_snapshot_portfolio_equity_missing_warning():
    """When equity is None and positions exist, warning added."""
    positions = [_pos(symbol="SPY", strike=500.0, contracts=1)]
    snap = build_portfolio_snapshot(positions, None)
    assert snap["exposure_pct"] is None
    assert any("PORTFOLIO_EQUITY" in w for w in snap["warnings"])


def test_load_open_positions_empty_file(tmp_path: Path):
    """load_open_positions returns [] for non-existent or empty ledger."""
    ledger = tmp_path / "open_positions.json"
    positions = load_open_positions(ledger)
    assert positions == []


def test_snapshot_cluster_breakdown_populated_from_mapping():
    """Phase 8.6: cluster_breakdown populated from symbol mapping when positions lack cluster."""
    positions = [
        _pos(symbol="AAPL", strike=150.0, contracts=1, mode="CC", shares=100, entry_spot=148.0),
        _pos(symbol="MSFT", strike=400.0, contracts=1),
    ]
    snap = build_portfolio_snapshot(positions, 200_000.0)
    assert "cluster_breakdown" in snap
    assert snap["cluster_breakdown"]["status"] in ("OK", "PARTIAL")
    by_cluster = snap["cluster_breakdown"]["by_cluster"]
    assert len(by_cluster) >= 1
    # Both AAPL and MSFT map to MEGA_CAP_TECH
    mega = next((c for c in by_cluster if c["cluster"] == "MEGA_CAP_TECH"), None)
    assert mega is not None
    assert mega["count"] == 2
    assert snap["max_cluster_pct"] is not None
    assert snap["max_cluster_pct"] == pytest.approx(100.0, rel=0.01)
    assert snap["cluster_risk_level"] == "MEDIUM"  # 2 in same cluster


def test_snapshot_sector_breakdown_ok_partial_unknown_thresholds():
    """Phase 8.6: sector_breakdown OK when >= 80% tagged, PARTIAL otherwise, UNKNOWN when none."""
    # All mapped (AAPL, MSFT, NVDA) -> OK
    positions_ok = [
        _pos(symbol="AAPL", strike=150.0, contracts=1),
        _pos(symbol="MSFT", strike=400.0, contracts=1),
        _pos(symbol="NVDA", strike=500.0, contracts=1),
    ]
    snap_ok = build_portfolio_snapshot(positions_ok, 500_000.0)
    assert snap_ok["sector_breakdown"]["status"] == "OK"

    # None mapped (all XYZ) -> UNKNOWN
    positions_unk = [
        _pos(symbol="XYZ", strike=100.0, contracts=1),
    ]
    snap_unk = build_portfolio_snapshot(positions_unk, 100_000.0)
    assert snap_unk["sector_breakdown"]["status"] == "UNKNOWN"

    # Mixed: 1 mapped, 2 unmapped -> 1/3 < 80% -> PARTIAL
    positions_partial = [
        _pos(symbol="AAPL", strike=150.0, contracts=1),
        _pos(symbol="XYZ", strike=100.0, contracts=1),
        _pos(symbol="ABC", strike=100.0, contracts=1),
    ]
    snap_partial = build_portfolio_snapshot(positions_partial, 200_000.0)
    assert snap_partial["sector_breakdown"]["status"] == "PARTIAL"
