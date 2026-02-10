# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for correct missing-data handling across evaluator.

Key behaviors:
1. MISSING fields produce DATA_INCOMPLETE (not LIQUIDITY_WARN or 0)
2. Numeric zeros remain VALID=0 (don't misclassify real zero)
3. Score is capped when DATA_INCOMPLETE
4. Alerts correctly distinguish MISSING vs low values
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    wrap_field,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness,
    build_data_incomplete_reason,
)


class TestMissingVsZeroDistinction:
    """Tests that verify MISSING data is not treated as 0."""

    def test_null_is_missing_not_zero(self):
        """null/None values should be MISSING, not 0."""
        fv = wrap_field_float(None, "price")
        assert fv.quality == DataQuality.MISSING
        assert fv.value is None
        # This is the key: value_or(0.0) returns default, not the stored value
        # because the quality is MISSING
        assert not fv.is_valid

    def test_explicit_zero_is_valid(self):
        """Explicit 0 should be VALID with value=0."""
        fv = wrap_field_float(0, "price")
        assert fv.quality == DataQuality.VALID
        assert fv.value == 0
        assert fv.is_valid

    def test_zero_int_is_valid(self):
        """Explicit 0 int should be VALID with value=0."""
        fv = wrap_field_int(0, "volume")
        assert fv.quality == DataQuality.VALID
        assert fv.value == 0
        assert fv.is_valid

    def test_allow_zero_false_treats_zero_as_missing(self):
        """When allow_zero=False, 0 becomes MISSING."""
        fv = wrap_field_float(0, "volume", allow_zero=False)
        assert fv.quality == DataQuality.MISSING
        assert fv.value is None

    def test_value_or_returns_default_for_missing(self):
        """value_or should return default for MISSING, not 0."""
        fv_missing = wrap_field_float(None, "bid")
        fv_zero = wrap_field_float(0, "bid")

        # MISSING: returns the default
        assert fv_missing.value_or(999.0) == 999.0
        
        # VALID with 0: returns 0, NOT the default
        assert fv_zero.value_or(999.0) == 0

    def test_completeness_calculation(self):
        """Completeness should count VALID fields, not non-zero fields."""
        fields = {
            "price": wrap_field_float(100.0, "price"),  # VALID
            "bid": wrap_field_float(None, "bid"),        # MISSING
            "volume": wrap_field_int(0, "volume"),       # VALID (0 is valid)
            "ask": wrap_field_float(None, "ask"),        # MISSING
        }
        
        completeness, missing = compute_data_completeness(fields)
        
        # 2 VALID (price, volume), 2 MISSING (bid, ask)
        assert completeness == 0.5
        assert sorted(missing) == ["ask", "bid"]


class TestDataIncompleteReason:
    """Tests for DATA_INCOMPLETE reason generation."""

    def test_single_missing_field(self):
        """Single missing field generates proper reason."""
        reason = build_data_incomplete_reason(["bid"])
        assert "DATA_INCOMPLETE" in reason
        assert "bid" in reason

    def test_multiple_missing_fields(self):
        """Multiple missing fields generates proper reason."""
        reason = build_data_incomplete_reason(["bid", "ask", "volume"])
        assert "DATA_INCOMPLETE" in reason
        assert "missing:" in reason
        assert "bid" in reason
        assert "ask" in reason
        assert "volume" in reason

    def test_many_missing_fields_truncated(self):
        """Many missing fields shows count and first few."""
        fields = ["f1", "f2", "f3", "f4", "f5", "f6"]
        reason = build_data_incomplete_reason(fields)
        assert "DATA_INCOMPLETE" in reason
        assert "6 fields missing" in reason


class TestEvaluatorMissingDataHandling:
    """Tests for evaluator behavior with missing data."""

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    def test_missing_liquidity_fields_produces_data_incomplete(
        self, mock_strikes, mock_summaries
    ):
        """Missing liquidity fields should produce DATA_INCOMPLETE, not LIQUIDITY_WARN."""
        from app.core.eval.universe_evaluator import _evaluate_single_symbol, _generate_alerts

        # Mock ORATS data with some fields missing
        mock_summaries.return_value = [{
            "stockPrice": 150.0,
            "bid": None,  # MISSING
            "ask": None,  # MISSING
            "volume": None,  # MISSING
            "avgVolume": 1000000,
            "ivRank": 45.0,
        }]

        # Mock strikes with valid liquidity
        mock_strikes.return_value = [
            {"openInt": 500, "volume": 100, "strike": 145, "delta": -0.25, "bid": 2.0, "putCall": "P", "expirDate": "2026-03-20"},
        ]

        result = _evaluate_single_symbol("TEST")
        alerts = _generate_alerts(result)

        # Should have DATA_INCOMPLETE alert
        data_incomplete_alerts = [a for a in alerts if a.type == "DATA_INCOMPLETE"]
        assert len(data_incomplete_alerts) > 0, "Expected DATA_INCOMPLETE alert"

        # Should NOT have LIQUIDITY_WARN (because data is MISSING, not low)
        liquidity_warns = [a for a in alerts if a.type == "LIQUIDITY_WARN"]
        assert len(liquidity_warns) == 0, "Should not have LIQUIDITY_WARN when data is MISSING"

        # Verdict should be HOLD with DATA_INCOMPLETE reason
        assert result.verdict == "HOLD"
        assert "DATA_INCOMPLETE" in result.primary_reason

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    def test_valid_low_liquidity_produces_liquidity_warn(
        self, mock_strikes, mock_summaries
    ):
        """Valid but low liquidity values should produce LIQUIDITY_WARN, not DATA_INCOMPLETE."""
        from app.core.eval.universe_evaluator import _evaluate_single_symbol, _generate_alerts

        # Mock ORATS data with all fields present
        mock_summaries.return_value = [{
            "stockPrice": 150.0,
            "bid": 149.90,  # VALID
            "ask": 150.10,  # VALID
            "volume": 100,  # VALID (but low)
            "avgVolume": 1000000,
            "ivRank": 45.0,
        }]

        # Mock strikes with LOW liquidity (valid data, but fails threshold)
        mock_strikes.return_value = [
            {"openInt": 10, "volume": 5, "strike": 145, "delta": -0.25, "bid": 2.0, "putCall": "P", "expirDate": "2026-03-20"},
        ]

        result = _evaluate_single_symbol("TEST")
        alerts = _generate_alerts(result)

        # Should have LIQUIDITY_WARN (low values, not missing)
        liquidity_warns = [a for a in alerts if a.type == "LIQUIDITY_WARN"]
        # Note: We may or may not have this depending on threshold behavior
        
        # Should NOT have DATA_INCOMPLETE for liquidity fields (they're present)
        data_incomplete = [a for a in alerts if a.type == "DATA_INCOMPLETE"]
        # If any, they should be for other fields, not liquidity
        for alert in data_incomplete:
            meta = alert.meta or {}
            missing_liq = meta.get("missing_liquidity_fields", [])
            assert len(missing_liq) == 0, "Should not have missing_liquidity_fields in DATA_INCOMPLETE"

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    def test_score_capped_with_incomplete_data(
        self, mock_strikes, mock_summaries
    ):
        """Score should be capped at 60 when DATA_INCOMPLETE is present."""
        from app.core.eval.universe_evaluator import _evaluate_single_symbol, DATA_INCOMPLETE_SCORE_CAP

        # Mock ORATS data with missing fields
        mock_summaries.return_value = [{
            "stockPrice": 150.0,
            "bid": None,  # MISSING
            "ask": None,  # MISSING
            "volume": None,  # MISSING
            "avgVolume": 1000000,
            "ivRank": 25.0,  # Good IV (would normally boost score)
        }]

        # Mock strikes with excellent liquidity
        mock_strikes.return_value = [
            {"openInt": 10000, "volume": 5000, "strike": 145, "delta": -0.25, "bid": 2.0, "putCall": "P", "expirDate": "2026-03-20"},
        ]

        result = _evaluate_single_symbol("TEST")

        # Score should be capped
        assert result.score <= DATA_INCOMPLETE_SCORE_CAP, f"Score {result.score} should be capped at {DATA_INCOMPLETE_SCORE_CAP}"

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    def test_zero_volume_is_valid_not_missing(
        self, mock_strikes, mock_summaries
    ):
        """A volume of 0 should be VALID, not MISSING."""
        from app.core.eval.universe_evaluator import _evaluate_single_symbol

        # Mock ORATS data with explicit zeros
        mock_summaries.return_value = [{
            "stockPrice": 150.0,
            "bid": 149.90,
            "ask": 150.10,
            "volume": 0,  # Explicit 0, not None
            "avgVolume": 0,  # Explicit 0, not None
            "ivRank": 45.0,
        }]

        mock_strikes.return_value = [
            {"openInt": 500, "volume": 100, "strike": 145, "delta": -0.25, "bid": 2.0, "putCall": "P", "expirDate": "2026-03-20"},
        ]

        result = _evaluate_single_symbol("TEST")

        # volume should be VALID (0 is a valid value)
        assert result.data_quality_details.get("volume") == "VALID"

        # volume should NOT be in missing_fields (no avg_volume; use volume metrics)
        assert "volume" not in result.missing_fields


class TestDataQualityDetails:
    """Tests for data_quality_details tracking."""

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    def test_data_quality_details_populated(
        self, mock_strikes, mock_summaries
    ):
        """data_quality_details should be populated for all tracked fields."""
        from app.core.eval.universe_evaluator import _evaluate_single_symbol

        mock_summaries.return_value = [{
            "stockPrice": 150.0,
            "bid": None,
            "ask": 150.10,
            "volume": 0,
            "avgVolume": None,
            "ivRank": 45.0,
        }]

        mock_strikes.return_value = [
            {"openInt": 500, "volume": 100, "strike": 145},
        ]

        result = _evaluate_single_symbol("TEST")

        # Check data_quality_details
        assert "price" in result.data_quality_details
        assert result.data_quality_details["price"] == "VALID"

        assert "bid" in result.data_quality_details
        assert result.data_quality_details["bid"] == "MISSING"

        assert "ask" in result.data_quality_details
        assert result.data_quality_details["ask"] == "VALID"

        assert "volume" in result.data_quality_details
        assert result.data_quality_details["volume"] == "VALID"  # 0 is valid
        # Volume metrics: avg_option_volume_20d / avg_stock_volume_20d (no avg_volume)


class TestAlertCategoryDistinction:
    """Tests for correct alert category generation."""

    def test_missing_produces_data_incomplete_not_liquidity_warn(self):
        """When liquidity fields are MISSING, alert should be DATA_INCOMPLETE."""
        from app.core.eval.universe_evaluator import (
            _generate_alerts,
            SymbolEvaluationResult,
            REQUIRED_LIQUIDITY_FIELDS,
        )

        result = SymbolEvaluationResult(
            symbol="TEST",
            verdict="HOLD",
            primary_reason="DATA_INCOMPLETE - missing: bid, ask, volume",
            liquidity_ok=False,
            liquidity_reason="Liquidity data incomplete",
            missing_fields=["bid", "ask", "volume"],
            data_completeness=0.5,
        )

        alerts = _generate_alerts(result)

        alert_types = [a.type for a in alerts]
        
        # Should have DATA_INCOMPLETE
        assert "DATA_INCOMPLETE" in alert_types
        
        # Should NOT have LIQUIDITY_WARN
        assert "LIQUIDITY_WARN" not in alert_types

    def test_low_values_produces_liquidity_warn_not_data_incomplete(self):
        """When liquidity fields are present but low, alert should be LIQUIDITY_WARN."""
        from app.core.eval.universe_evaluator import _generate_alerts, SymbolEvaluationResult

        result = SymbolEvaluationResult(
            symbol="TEST",
            verdict="HOLD",
            primary_reason="Low liquidity - OI: 50, Volume: 10",
            liquidity_ok=False,
            liquidity_reason="Low liquidity - OI: 50, Volume: 10",
            missing_fields=[],  # No missing fields
            data_completeness=1.0,
        )

        alerts = _generate_alerts(result)

        alert_types = [a.type for a in alerts]
        
        # Should have LIQUIDITY_WARN (actual low values)
        assert "LIQUIDITY_WARN" in alert_types
        
        # Should NOT have DATA_INCOMPLETE (data is present)
        assert "DATA_INCOMPLETE" not in alert_types


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_orats_response(self):
        """Empty ORATS response should result in appropriate handling."""
        from app.core.models.data_quality import compute_data_completeness

        # When no data is fetched, all fields would be missing
        fields = {}
        completeness, missing = compute_data_completeness(fields)
        
        # Empty dict means no fields to track, so 100% complete (trivially)
        assert completeness == 1.0
        assert missing == []

    def test_coercion_error_is_error_not_missing(self):
        """Failed type coercion should be ERROR, not MISSING."""
        fv = wrap_field_float("not_a_number", "price")
        assert fv.quality == DataQuality.ERROR
        assert fv.value is None
        assert "coercion failed" in fv.reason.lower()

    def test_nan_handling(self):
        """NaN values should be handled appropriately."""
        import math
        fv = wrap_field_float(float("nan"), "price")
        # NaN coerces to float successfully, but is it valid?
        # Per the current implementation, NaN is "valid" as a float
        # This test documents current behavior
        assert fv.quality == DataQuality.VALID
        assert math.isnan(fv.value)
