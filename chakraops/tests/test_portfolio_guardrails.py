# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for portfolio-level risk caps (Phase 2.5)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.execution_guard import check_portfolio_caps
from app.core.models.position import Position


def _position(symbol: str, strike: float = 100.0, contracts: int = 1) -> Position:
    return Position(
        id=f"pos-{symbol}",
        symbol=symbol.upper(),
        position_type="CSP",
        strike=strike,
        expiry="2026-03-21",
        contracts=contracts,
        premium_collected=300.0,
        entry_date=datetime.now(timezone.utc).isoformat(),
        status="OPEN",
        state="OPEN",
        state_history=[],
        notes=None,
        exit_plan=None,
    )


class TestMaxPositions:
    """Block new trades if current active positions >= max_active_positions."""

    def test_max_positions_block(self):
        """When open positions >= max_active_positions, return max_positions."""
        open_positions = [_position("AAPL"), _position("MSFT"), _position("GOOG"), _position("AMZN"), _position("NVDA")]
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        candidate = {"symbol": "META", "strike": 200.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "max_positions" in reasons
        assert len(reasons) == 1

    def test_max_positions_allow(self):
        """When open positions < max_active_positions, do not block on max_positions."""
        open_positions = [_position("AAPL"), _position("MSFT")]
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        candidate = {"symbol": "GOOG", "strike": 150.0, "contracts": 1, "premium_collected": 400.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "max_positions" not in reasons


class TestRiskBudget:
    """Block if trade estimated max loss > max_risk_per_trade_pct * account_balance."""

    def test_risk_budget_block(self):
        """When estimated max loss > 1% of account, return risk_budget."""
        open_positions = []
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        # Max loss = 500 * 100 * 1 - 500 = 49_500; 1% of 100k = 1_000; 49_500 > 1_000
        candidate = {"symbol": "SPY", "strike": 500.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "risk_budget" in reasons

    def test_risk_budget_allow(self):
        """When estimated max loss <= budget, do not block on risk_budget."""
        open_positions = []
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        # Max loss = 100*100*1 - 500 = 9_500; 1% of 1M = 10_000; 9_500 < 10_000
        candidate = {"symbol": "AAPL", "strike": 100.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 1_000_000.0, config)
        assert "risk_budget" not in reasons


class TestSectorCap:
    """Block if open positions in same sector >= max_sector_positions."""

    def test_sector_cap_block(self):
        """When same-sector count >= max_sector_positions, return sector_cap."""
        open_positions = [
            _position("AAPL"),  # Tech
            _position("MSFT"),  # Tech
        ]
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {"AAPL": "Technology", "MSFT": "Technology", "GOOG": "Technology"},
        }
        # Use small strike so risk_budget does not trigger (max loss 995 < 1% of 100k)
        candidate = {"symbol": "GOOG", "strike": 10.0, "contracts": 1, "premium_collected": 5.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "sector_cap" in reasons

    def test_sector_cap_allow(self):
        """When same-sector count < max_sector_positions, do not block on sector_cap."""
        open_positions = [_position("AAPL")]
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
        }
        candidate = {"symbol": "MSFT", "strike": 200.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "sector_cap" not in reasons


class TestDeltaExposure:
    """Block if (sum |deltas| notional + candidate) / account_value > max_total_delta_exposure."""

    def test_delta_exposure_block(self):
        """When total delta notional / account > 0.30, return delta_exposure."""
        open_positions = [
            _position("AAPL"),  # 1 * 100 * 0.25 = 25
            _position("MSFT"),  # 1 * 100 * 0.25 = 25
        ]
        # Current ~ 50; candidate 1*100*0.25 = 25; total 75. 75/100 = 0.75 > 0.30
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1000.0,  # Relax so risk_budget does not trigger
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {"AAPL": "Tech", "MSFT": "Finance", "GOOG": "Tech"},  # AAPL+GOOG=2 in Tech but we check candidate's sector; GOOG in Tech with only AAPL = 1, so sector_cap passes
        }
        candidate = {"symbol": "GOOG", "strike": 10.0, "contracts": 1, "premium_collected": 5.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100.0, config)
        assert "delta_exposure" in reasons

    def test_delta_exposure_allow(self):
        """When total delta notional / account <= 0.30, do not block on delta_exposure."""
        open_positions = []
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        candidate = {"symbol": "AAPL", "strike": 100.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 100_000.0, config)
        assert "delta_exposure" not in reasons


class TestAllCapsPass:
    """When no cap is exceeded, return empty list."""

    def test_all_pass(self):
        """Empty positions, small candidate, no sector overlap -> no reasons."""
        open_positions = []
        config = {
            "max_active_positions": 5,
            "max_risk_per_trade_pct": 1.0,
            "max_sector_positions": 2,
            "max_total_delta_exposure": 0.30,
            "sector_map": {},
        }
        # Max loss = 100*100 - 500 = 9_500; 1% of 1M = 10_000; 9_500 < 10_000 so risk_budget passes
        candidate = {"symbol": "AAPL", "strike": 100.0, "contracts": 1, "premium_collected": 500.0, "delta": -0.25}
        reasons = check_portfolio_caps(open_positions, candidate, 1_000_000.0, config)
        assert reasons == []
