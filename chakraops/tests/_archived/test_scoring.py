# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Scoring and capital-efficiency tests."""

import os
import pytest
from app.core.eval.scoring import (
    capital_efficiency_score,
    data_quality_score,
    regime_score,
    options_liquidity_score,
    strategy_fit_score,
    compute_score_breakdown,
    build_rank_reasons,
    ScoreBreakdown,
    get_account_equity,
    get_notional_thresholds,
    get_notional_penalties,
    get_high_price_config,
    get_band_limits,
)
from app.core.eval.confidence_band import compute_confidence_band, CapitalHint


class TestCapitalEfficiencyScore:
    """capital_efficiency_score: notional_pct bands and high_price penalty."""

    def test_no_account_equity_no_penalty(self):
        """When account_equity is not set, only high_price penalty can apply."""
        score, penalties, top = capital_efficiency_score(
            csp_notional=50_000,
            account_equity=None,
            price=100.0,
        )
        assert score == 100
        assert penalties == []
        assert top is None

    def test_no_account_equity_high_price_penalty(self):
        """High underlying price penalizes even without account_equity."""
        score, penalties, top = capital_efficiency_score(
            csp_notional=None,
            account_equity=None,
            price=500.0,  # above default 400
        )
        assert score == 90  # 100 - 10
        assert any("High underlying" in p for p in penalties)
        assert top is not None and "High" in top

    def test_notional_warn_band(self):
        """notional_pct in [warn_above, heavy_penalty_above) applies warn penalty."""
        # 5% = 0.05 -> warn (default 5 pts)
        score, penalties, top = capital_efficiency_score(
            csp_notional=5_000,   # 5% of 100k
            account_equity=100_000,
            price=50.0,
        )
        assert score == 95
        assert any("5.0%" in p or "5%" in p for p in penalties)
        assert top is not None

    def test_notional_heavy_penalty_band(self):
        """notional_pct in [heavy_penalty_above, cap_above) applies heavy penalty."""
        # 12% of account -> heavy (default 15 pts)
        score, penalties, _ = capital_efficiency_score(
            csp_notional=12_000,
            account_equity=100_000,
            price=100.0,
        )
        assert score == 85
        assert any("12" in p for p in penalties)

    def test_notional_cap_band(self):
        """notional_pct >= cap_above applies cap penalty."""
        # 25% of account -> cap (default 30 pts)
        score, penalties, _ = capital_efficiency_score(
            csp_notional=25_000,
            account_equity=100_000,
            price=200.0,
        )
        assert score == 70
        assert any("cap" in p.lower() for p in penalties)

    def test_high_price_plus_notional_penalty(self):
        """Both high price and notional can apply."""
        score, penalties, _ = capital_efficiency_score(
            csp_notional=15_000,  # 15% -> heavy 15
            account_equity=100_000,
            price=500.0,          # high price 10
        )
        assert score == 75  # 100 - 15 - 10
        assert len(penalties) >= 2


class TestComponentScores:
    """Component score helpers (0-100)."""

    def test_data_quality_score(self):
        assert data_quality_score(1.0) == 100
        assert data_quality_score(0.75) == 75
        assert data_quality_score(0.0) == 0

    def test_regime_score(self):
        assert regime_score("RISK_ON") == 100
        assert regime_score("NEUTRAL") == 65
        assert regime_score("RISK_OFF") == 50
        assert regime_score(None) == 50

    def test_options_liquidity_score(self):
        assert options_liquidity_score(True, "A") == 100
        assert options_liquidity_score(True, "B") == 80
        assert options_liquidity_score(True, "C") == 60
        assert options_liquidity_score(False, "A") == 20

    def test_strategy_fit_score(self):
        assert strategy_fit_score("ELIGIBLE", False) == 100
        assert strategy_fit_score("ELIGIBLE", True) == 70
        assert strategy_fit_score("HOLD", False) == 50
        assert strategy_fit_score("BLOCKED", False) == 20


class TestScoreBreakdownAndRankReasons:
    """compute_score_breakdown and build_rank_reasons."""

    def test_breakdown_has_all_components(self):
        breakdown, composite = compute_score_breakdown(
            data_completeness=0.9,
            regime="RISK_ON",
            liquidity_ok=True,
            liquidity_grade="A",
            verdict="ELIGIBLE",
            position_open=False,
            price=150.0,
            selected_put_strike=145.0,
        )
        assert breakdown.data_quality_score == 90
        assert breakdown.regime_score == 100
        assert breakdown.options_liquidity_score == 100
        assert breakdown.strategy_fit_score == 100
        assert 0 <= breakdown.capital_efficiency_score <= 100
        assert 0 <= composite <= 100
        assert "data_quality_score" in breakdown.to_dict()
        assert "composite_score" in breakdown.to_dict()

    def test_rank_reasons_structure(self):
        breakdown, _ = compute_score_breakdown(
            data_completeness=0.9,
            regime="RISK_ON",
            liquidity_ok=True,
            liquidity_grade="A",
            verdict="ELIGIBLE",
            position_open=False,
            price=100.0,
            selected_put_strike=None,
        )
        reasons = build_rank_reasons(breakdown, "RISK_ON", 0.9, True, "ELIGIBLE")
        assert "reasons" in reasons
        assert "penalty" in reasons
        assert isinstance(reasons["reasons"], list)
        assert len(reasons["reasons"]) <= 3


class TestBandAssignmentAndReason:
    """Band A/B/C and band_reason (Phase 3)."""

    def test_band_a_has_reason(self):
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.95,
            liquidity_ok=True,
            score=80,
            position_open=False,
        )
        assert hint.band == "A"
        assert hint.band_reason is not None
        assert "Band A" in hint.band_reason

    def test_band_c_reason_explains_why(self):
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.70,
            liquidity_ok=True,
            score=72,
            position_open=False,
        )
        assert hint.band == "C"
        assert hint.band_reason is not None
        assert "0.70" in hint.band_reason or "0.75" in hint.band_reason

    def test_band_c_low_score_reason(self):
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.95,
            liquidity_ok=True,
            score=55,
            position_open=False,
        )
        assert hint.band == "C"
        assert "score" in hint.band_reason.lower()
        assert "60" in hint.band_reason

    def test_band_b_reason(self):
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="NEUTRAL",
            data_completeness=0.95,
            liquidity_ok=True,
            score=70,
            position_open=False,
        )
        assert hint.band == "B"
        assert hint.band_reason is not None
        assert "regime" in hint.band_reason.lower() or "NEUTRAL" in hint.band_reason
