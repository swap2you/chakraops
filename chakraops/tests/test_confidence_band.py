# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: Confidence band and capital hint tests."""

import pytest
from app.core.eval.confidence_band import (
    ConfidenceBand,
    CapitalHint,
    BAND_CAPITAL_PCT,
    compute_confidence_band,
)


class TestBandAssignment:
    """Band A/B/C assignment rules."""

    def test_band_a_risk_on_eligible_strong_data(self):
        """A: RISK_ON, ELIGIBLE, data complete, liquidity ok."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.95,
            liquidity_ok=True,
            score=78,
            position_open=False,
        )
        assert hint.band == "A"
        assert hint.suggested_capital_pct == BAND_CAPITAL_PCT[ConfidenceBand.A]

    def test_band_b_neutral_regime(self):
        """B: NEUTRAL regime even when ELIGIBLE and data ok."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="NEUTRAL",
            data_completeness=0.95,
            liquidity_ok=True,
            score=65,
            position_open=False,
        )
        assert hint.band == "B"

    def test_band_b_data_gaps(self):
        """B: ELIGIBLE with data_completeness < 0.9."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.80,
            liquidity_ok=True,
            score=75,
            position_open=False,
        )
        assert hint.band == "B"

    def test_band_c_hold_barely_passed(self):
        """C: HOLD with score 50-65."""
        hint = compute_confidence_band(
            verdict="HOLD",
            regime="NEUTRAL",
            data_completeness=0.7,
            liquidity_ok=False,
            score=55,
            position_open=False,
        )
        assert hint.band == "C"

    def test_band_c_blocked(self):
        """C: BLOCKED verdict."""
        hint = compute_confidence_band(
            verdict="BLOCKED",
            regime="RISK_ON",
            data_completeness=1.0,
            liquidity_ok=True,
            score=40,
            position_open=False,
        )
        assert hint.band == "C"

    def test_band_c_data_incomplete_eligible(self):
        """C: ELIGIBLE but data_completeness < 0.75."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.70,
            liquidity_ok=True,
            score=72,
            position_open=False,
        )
        assert hint.band == "C"


class TestRegimeImpact:
    """Regime downgrades band."""

    def test_risk_off_eligible_still_c_or_b(self):
        """ELIGIBLE with RISK_OFF would be capped to HOLD in practice; if passed as ELIGIBLE, regime affects band."""
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_OFF",
            data_completeness=0.95,
            liquidity_ok=True,
            score=50,
            position_open=False,
        )
        assert hint.band == "B"


class TestDataCompletenessDowngrade:
    """Data completeness < 0.75 forces C."""

    def test_low_completeness_eligible_c(self):
        hint = compute_confidence_band(
            verdict="ELIGIBLE",
            regime="RISK_ON",
            data_completeness=0.60,
            liquidity_ok=True,
            score=70,
            position_open=False,
        )
        assert hint.band == "C"
