# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Tests for portfolio — aggregation, exposure, risk profile, risk checks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.accounts.models import Account
from app.core.positions.models import Position
from app.core.portfolio.models import RiskProfile
from app.core.portfolio.store import load_risk_profile, save_risk_profile, update_risk_profile
from app.core.portfolio.service import compute_portfolio_summary, compute_exposure
from app.core.portfolio.risk import evaluate_risk_flags, would_exceed_limits
from app.core.market.company_data import get_sector


class TestPortfolioAggregation:
    """Portfolio aggregation math — equity, in use, available."""

    def test_total_equity_sum(self):
        accounts = [
            Account(
                account_id="a1",
                provider="Manual",
                account_type="Taxable",
                total_capital=100000,
                max_capital_per_trade_pct=5,
                max_total_exposure_pct=30,
                allowed_strategies=["CSP"],
            ),
            Account(
                account_id="a2",
                provider="Manual",
                account_type="Roth",
                total_capital=50000,
                max_capital_per_trade_pct=5,
                max_total_exposure_pct=30,
                allowed_strategies=["CSP"],
            ),
        ]
        positions = []
        summary = compute_portfolio_summary(accounts, positions)
        assert summary.total_equity == 150000
        assert summary.capital_in_use == 0
        assert summary.available_capital == 150000
        assert summary.capital_utilization_pct == 0

    def test_capital_in_use_csp(self):
        accounts = [
            Account(
                account_id="a1",
                provider="Manual",
                account_type="Taxable",
                total_capital=100000,
                max_capital_per_trade_pct=5,
                max_total_exposure_pct=30,
                allowed_strategies=["CSP"],
            ),
        ]
        positions = [
            Position(
                position_id="p1",
                account_id="a1",
                symbol="NVDA",
                strategy="CSP",
                contracts=2,
                strike=170.0,
                status="OPEN",
            ),
        ]
        summary = compute_portfolio_summary(accounts, positions)
        # CSP: strike * 100 * contracts = 170 * 100 * 2 = 34000
        assert summary.capital_in_use == 34000
        assert summary.available_capital == 66000
        assert summary.capital_utilization_pct == pytest.approx(0.34, rel=0.01)

    def test_available_capital_clamped(self):
        accounts = [
            Account(
                account_id="a1",
                provider="Manual",
                account_type="Taxable",
                total_capital=50000,
                max_capital_per_trade_pct=5,
                max_total_exposure_pct=30,
                allowed_strategies=["CSP"],
            ),
        ]
        positions = [
            Position(
                position_id="p1",
                account_id="a1",
                symbol="NVDA",
                strategy="CSP",
                contracts=10,
                strike=170.0,
                status="OPEN",
            ),
        ]
        summary = compute_portfolio_summary(accounts, positions)
        # 10 * 170 * 100 = 170000 > 50000
        assert summary.capital_in_use == 170000
        assert summary.available_capital == 0
        assert summary.available_capital_clamped is True


class TestExposureGrouping:
    """Exposure grouping and percent math."""

    def test_exposure_by_symbol(self):
        accounts = [
            Account(account_id="a1", provider="Manual", account_type="Taxable", total_capital=100000,
                    max_capital_per_trade_pct=5, max_total_exposure_pct=30, allowed_strategies=["CSP"]),
        ]
        positions = [
            Position(position_id="p1", account_id="a1", symbol="NVDA", strategy="CSP",
                     contracts=2, strike=170.0, status="OPEN"),
            Position(position_id="p2", account_id="a1", symbol="AAPL", strategy="CSP",
                     contracts=1, strike=150.0, status="OPEN"),
        ]
        items = compute_exposure(accounts, positions, group_by="symbol")
        assert len(items) == 2
        syms = {i["key"]: i for i in items}
        assert "NVDA" in syms
        assert "AAPL" in syms
        assert syms["NVDA"]["required_capital"] == 34000
        assert syms["AAPL"]["required_capital"] == 15000


class TestRiskProfilePersistence:
    """Risk profile JSON persistence."""

    def test_load_defaults_when_missing(self, tmp_path):
        with patch("app.core.portfolio.store._risk_profile_path", return_value=tmp_path / "missing.json"):
            p = load_risk_profile()
        assert p.max_capital_utilization_pct == 0.35
        assert p.max_open_positions == 12

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "risk_profile.json"
        with patch("app.core.portfolio.store._risk_profile_path", return_value=path):
            p = RiskProfile(max_capital_utilization_pct=0.40, max_open_positions=8)
            save_risk_profile(p)
            loaded = load_risk_profile()
        assert loaded.max_capital_utilization_pct == 0.40
        assert loaded.max_open_positions == 8


class TestRiskChecks:
    """Risk checks — symbol/sector/utilization limits."""

    def test_over_utilization_flag(self):
        profile = RiskProfile(max_capital_utilization_pct=0.35)
        flags = evaluate_risk_flags(
            total_equity=100000,
            capital_in_use=40000,
            available_capital=60000,
            open_positions_count=2,
            exposure_by_symbol={"NVDA": 40000},
            exposure_by_sector={"Technology": 40000},
            profile=profile,
            positions_by_sector={"Technology": 2},
        )
        codes = [f.code for f in flags]
        assert "OVER_UTILIZATION" in codes

    def test_would_exceed_limits(self):
        profile = RiskProfile(max_capital_utilization_pct=0.35)
        would, reasons = would_exceed_limits(
            profile=profile,
            total_equity=100000,
            capital_in_use=30000,
            open_positions_count=2,
            exposure_by_symbol={"NVDA": 30000},
            exposure_by_sector={"Technology": 30000},
            positions_by_sector={"Technology": 2},
            candidate_symbol="NVDA",
            candidate_capital=10000,  # would push NVDA to 40k = 40% of equity
            candidate_sector="Technology",
        )
        assert would
        assert any("symbol" in r.lower() or "utilization" in r.lower() for r in reasons)


class TestSectorLookup:
    """Sector lookup returns Unknown for missing."""

    def test_get_sector_known(self):
        assert get_sector("NVDA") == "Technology"
        assert get_sector("AAPL") == "Technology"

    def test_get_sector_unknown(self):
        assert get_sector("UNKNOWNTICKER") == "Unknown"
