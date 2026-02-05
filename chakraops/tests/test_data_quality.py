# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for data quality model - ensuring missing != 0 and proper propagation."""

import pytest
from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    ReasonCode,
    wrap_field,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness,
    build_data_incomplete_reason,
)


class TestDataQualityEnum:
    """Tests for DataQuality enum."""

    def test_enum_values(self):
        """DataQuality has exactly VALID, MISSING, ERROR."""
        assert DataQuality.VALID.value == "VALID"
        assert DataQuality.MISSING.value == "MISSING"
        assert DataQuality.ERROR.value == "ERROR"

    def test_enum_string_conversion(self):
        """DataQuality converts to string correctly."""
        assert str(DataQuality.VALID) == "VALID"
        assert str(DataQuality.MISSING) == "MISSING"
        assert str(DataQuality.ERROR) == "ERROR"

    def test_enum_comparison(self):
        """DataQuality can be compared as string."""
        assert DataQuality.VALID == "VALID"
        assert DataQuality.MISSING == "MISSING"


class TestFieldValueWrapper:
    """Tests for FieldValue wrapper."""

    def test_valid_field(self):
        """FieldValue with valid data."""
        fv = FieldValue(value=100.0, quality=DataQuality.VALID, field_name="price")
        assert fv.is_valid is True
        assert fv.is_missing is False
        assert fv.is_error is False
        assert fv.value == 100.0

    def test_missing_field(self):
        """FieldValue with missing data."""
        fv = FieldValue(value=None, quality=DataQuality.MISSING, field_name="bid")
        assert fv.is_valid is False
        assert fv.is_missing is True
        assert fv.is_error is False
        assert fv.value is None

    def test_error_field(self):
        """FieldValue with error."""
        fv = FieldValue(value=None, quality=DataQuality.ERROR, reason="Timeout", field_name="ask")
        assert fv.is_valid is False
        assert fv.is_missing is False
        assert fv.is_error is True
        assert fv.reason == "Timeout"

    def test_value_or_with_valid(self):
        """value_or returns value when valid."""
        fv = FieldValue(value=50, quality=DataQuality.VALID)
        assert fv.value_or(default=0) == 50

    def test_value_or_with_missing(self):
        """value_or returns default when missing."""
        fv = FieldValue(value=None, quality=DataQuality.MISSING)
        assert fv.value_or(default=999) == 999

    def test_value_or_with_error(self):
        """value_or returns default when error."""
        fv = FieldValue(value=None, quality=DataQuality.ERROR)
        assert fv.value_or(default=-1) == -1

    def test_to_dict(self):
        """FieldValue serializes to dict for API."""
        fv = FieldValue(value=42.5, quality=DataQuality.VALID, reason="", field_name="price")
        d = fv.to_dict()
        assert d["value"] == 42.5
        assert d["quality"] == "VALID"
        assert d["field_name"] == "price"


class TestWrapField:
    """Tests for wrap_field function - the core missing != 0 logic."""

    def test_null_becomes_missing_not_zero(self):
        """CRITICAL: None must become MISSING, not 0."""
        fv = wrap_field(None, "volume")
        assert fv.quality == DataQuality.MISSING
        assert fv.value is None
        # NOT 0!
        assert fv.value != 0

    def test_zero_stays_zero_when_valid(self):
        """Zero is a valid value, not missing."""
        fv = wrap_field(0, "count")
        assert fv.quality == DataQuality.VALID
        assert fv.value == 0

    def test_zero_can_be_treated_as_missing(self):
        """allow_zero=False treats 0 as missing."""
        fv = wrap_field(0, "volume", allow_zero=False)
        assert fv.quality == DataQuality.MISSING
        assert fv.value is None

    def test_valid_float_coercion(self):
        """Float coercion works."""
        fv = wrap_field("123.45", "price", coerce_to=float)
        assert fv.quality == DataQuality.VALID
        assert fv.value == 123.45

    def test_invalid_coercion_becomes_error(self):
        """Invalid coercion becomes ERROR, not 0."""
        fv = wrap_field("not_a_number", "price", coerce_to=float)
        assert fv.quality == DataQuality.ERROR
        assert fv.value is None
        assert "coercion failed" in fv.reason

    def test_wrap_field_float_convenience(self):
        """wrap_field_float convenience function."""
        fv = wrap_field_float(None, "bid")
        assert fv.quality == DataQuality.MISSING
        
        fv2 = wrap_field_float(99.5, "ask")
        assert fv2.quality == DataQuality.VALID
        assert fv2.value == 99.5

    def test_wrap_field_int_convenience(self):
        """wrap_field_int convenience function."""
        fv = wrap_field_int(None, "volume")
        assert fv.quality == DataQuality.MISSING
        
        fv2 = wrap_field_int(1000, "volume")
        assert fv2.quality == DataQuality.VALID
        assert fv2.value == 1000


class TestMissingNotTreatedAsZero:
    """
    CRITICAL TEST: Ensures the system never treats missing data as zero.
    This is the core guardrail for data quality.
    """

    def test_missing_price_is_not_zero(self):
        """A missing price is not the same as a $0 price."""
        # ORATS returns no stockPrice field
        orats_data = {"symbol": "XYZ"}
        fv = wrap_field_float(orats_data.get("stockPrice"), "price")
        
        assert fv.quality == DataQuality.MISSING
        assert fv.value is None
        # This is the key assertion - missing is not 0
        assert fv.value != 0
        
    def test_missing_volume_is_not_zero(self):
        """A missing volume is not the same as 0 volume."""
        orats_data = {"symbol": "XYZ", "stockPrice": 100.0}
        fv = wrap_field_int(orats_data.get("volume"), "volume")
        
        assert fv.quality == DataQuality.MISSING
        # Missing volume should not be treated as 0 for liquidity calculations
        assert fv.value is None
        
    def test_actual_zero_volume_is_different_from_missing(self):
        """A stock with 0 volume is different from missing volume data."""
        # Case 1: Explicitly 0 volume (halted stock, etc.)
        fv_zero = wrap_field_int(0, "volume")
        assert fv_zero.quality == DataQuality.VALID
        assert fv_zero.value == 0
        
        # Case 2: Missing volume data
        fv_missing = wrap_field_int(None, "volume")
        assert fv_missing.quality == DataQuality.MISSING
        assert fv_missing.value is None
        
        # They are NOT equivalent
        assert fv_zero.quality != fv_missing.quality

    def test_missing_bid_ask_should_not_compute_spread(self):
        """If bid or ask is missing, spread should not be computed as valid."""
        bid = wrap_field_float(None, "bid")
        ask = wrap_field_float(100.0, "ask")
        
        # Cannot compute spread when bid is missing
        if bid.is_missing:
            spread = None  # Correct behavior
        else:
            spread = ask.value - bid.value  # Would be wrong
            
        assert spread is None


class TestComputeDataCompleteness:
    """Tests for compute_data_completeness function."""

    def test_all_valid_is_100_percent(self):
        """All valid fields = 100% completeness."""
        fields = {
            "price": FieldValue(100.0, DataQuality.VALID, field_name="price"),
            "bid": FieldValue(99.5, DataQuality.VALID, field_name="bid"),
            "ask": FieldValue(100.5, DataQuality.VALID, field_name="ask"),
        }
        completeness, missing = compute_data_completeness(fields)
        assert completeness == 1.0
        assert missing == []

    def test_one_missing_reduces_completeness(self):
        """One missing field reduces completeness."""
        fields = {
            "price": FieldValue(100.0, DataQuality.VALID, field_name="price"),
            "bid": FieldValue(None, DataQuality.MISSING, field_name="bid"),
            "ask": FieldValue(100.5, DataQuality.VALID, field_name="ask"),
        }
        completeness, missing = compute_data_completeness(fields)
        assert completeness == pytest.approx(2/3)
        assert missing == ["bid"]

    def test_all_missing_is_0_percent(self):
        """All missing fields = 0% completeness."""
        fields = {
            "price": FieldValue(None, DataQuality.MISSING, field_name="price"),
            "volume": FieldValue(None, DataQuality.MISSING, field_name="volume"),
        }
        completeness, missing = compute_data_completeness(fields)
        assert completeness == 0.0
        assert set(missing) == {"price", "volume"}

    def test_error_counts_as_not_valid(self):
        """ERROR quality counts as not valid for completeness."""
        fields = {
            "price": FieldValue(None, DataQuality.ERROR, field_name="price"),
            "bid": FieldValue(99.5, DataQuality.VALID, field_name="bid"),
        }
        completeness, missing = compute_data_completeness(fields)
        assert completeness == 0.5
        assert "price" in missing


class TestBuildDataIncompleteReason:
    """Tests for build_data_incomplete_reason function."""

    def test_no_missing_returns_empty(self):
        """No missing fields returns empty string."""
        reason = build_data_incomplete_reason([])
        assert reason == ""

    def test_single_missing_field(self):
        """Single missing field message."""
        reason = build_data_incomplete_reason(["bid"])
        assert "DATA_INCOMPLETE" in reason
        assert "bid" in reason

    def test_multiple_missing_fields(self):
        """Multiple missing fields message."""
        reason = build_data_incomplete_reason(["bid", "ask", "volume"])
        assert "DATA_INCOMPLETE" in reason
        assert "bid" in reason
        assert "ask" in reason
        assert "volume" in reason

    def test_many_missing_fields_truncated(self):
        """Many missing fields are truncated."""
        fields = ["f1", "f2", "f3", "f4", "f5", "f6"]
        reason = build_data_incomplete_reason(fields)
        assert "DATA_INCOMPLETE" in reason
        assert "..." in reason or "more" in reason


class TestReasonCodeConstants:
    """Tests for ReasonCode constants."""

    def test_data_incomplete_constant(self):
        """DATA_INCOMPLETE constant exists."""
        assert ReasonCode.DATA_INCOMPLETE == "DATA_INCOMPLETE"

    def test_other_reason_codes(self):
        """Other reason codes exist."""
        assert ReasonCode.DATA_STALE == "DATA_STALE"
        assert ReasonCode.DATA_ERROR == "DATA_ERROR"
        assert ReasonCode.FIELD_MISSING == "FIELD_MISSING"


class TestReasonPropagationInEvaluator:
    """
    Tests that DATA_INCOMPLETE propagates through the evaluator output schema.
    These tests use the actual evaluator data structures.
    """

    def test_symbol_result_has_data_quality_fields(self):
        """SymbolEvaluationResult has data quality tracking fields."""
        from app.core.eval.universe_evaluator import SymbolEvaluationResult
        
        result = SymbolEvaluationResult(symbol="TEST")
        # New fields should exist
        assert hasattr(result, "data_completeness")
        assert hasattr(result, "missing_fields")
        assert hasattr(result, "data_quality_details")
        
        # Defaults
        assert result.data_completeness == 1.0
        assert result.missing_fields == []
        assert result.data_quality_details == {}

    def test_data_incomplete_in_primary_reason(self):
        """DATA_INCOMPLETE appears in primary_reason when liquidity fields are MISSING."""
        from app.core.eval.universe_evaluator import SymbolEvaluationResult, _determine_verdict
        
        result = SymbolEvaluationResult(
            symbol="TEST",
            options_available=True,
            liquidity_ok=True,  # Even if liquidity_ok=True, missing liquidity fields override
            data_completeness=0.5,
            missing_fields=["bid", "ask", "volume"],  # These are REQUIRED_LIQUIDITY_FIELDS
        )
        
        verdict, reason = _determine_verdict(result)
        # When required liquidity fields are MISSING, verdict should be HOLD
        # This is correct behavior: missing data != low liquidity
        assert verdict == "HOLD"
        assert "DATA_INCOMPLETE" in reason

    def test_alert_type_data_incomplete_exists(self):
        """DATA_INCOMPLETE is a valid alert type."""
        from app.core.eval.universe_evaluator import Alert
        
        alert = Alert(
            id="test_123",
            type="DATA_INCOMPLETE",
            symbol="TEST",
            message="Test message",
            severity="WARN",
        )
        assert alert.type == "DATA_INCOMPLETE"

    def test_generate_alerts_includes_data_incomplete(self):
        """_generate_alerts creates DATA_INCOMPLETE alerts when appropriate."""
        from app.core.eval.universe_evaluator import SymbolEvaluationResult, _generate_alerts
        
        result = SymbolEvaluationResult(
            symbol="TEST",
            verdict="ELIGIBLE",
            score=75,
            data_completeness=0.5,
            missing_fields=["bid", "ask", "volume"],
        )
        
        alerts = _generate_alerts(result)
        
        # Should have DATA_INCOMPLETE alert
        incomplete_alerts = [a for a in alerts if a.type == "DATA_INCOMPLETE"]
        assert len(incomplete_alerts) == 1
        
        alert = incomplete_alerts[0]
        assert "TEST" in alert.message
        assert "incomplete" in alert.message.lower()
        assert alert.severity == "WARN"
        assert alert.meta["completeness"] == 0.5
        assert "bid" in alert.meta["missing_fields"]

    def test_no_data_incomplete_alert_when_complete(self):
        """No DATA_INCOMPLETE alert when data is complete."""
        from app.core.eval.universe_evaluator import SymbolEvaluationResult, _generate_alerts
        
        result = SymbolEvaluationResult(
            symbol="TEST",
            verdict="ELIGIBLE",
            score=80,
            data_completeness=1.0,
            missing_fields=[],
        )
        
        alerts = _generate_alerts(result)
        
        # Should NOT have DATA_INCOMPLETE alert
        incomplete_alerts = [a for a in alerts if a.type == "DATA_INCOMPLETE"]
        assert len(incomplete_alerts) == 0


class TestEndToEndDataQuality:
    """
    End-to-end tests for data quality propagation.
    """

    def test_missing_orats_fields_tracked_correctly(self):
        """Simulates ORATS returning partial data."""
        # Simulate ORATS response with missing fields
        orats_response = {
            "stockPrice": 150.0,
            # bid, ask, volume not provided
        }
        
        price = wrap_field_float(orats_response.get("stockPrice"), "price")
        bid = wrap_field_float(orats_response.get("bid"), "bid")
        ask = wrap_field_float(orats_response.get("ask"), "ask")
        volume = wrap_field_int(orats_response.get("volume"), "volume")
        
        fields = {
            "price": price,
            "bid": bid,
            "ask": ask,
            "volume": volume,
        }
        
        completeness, missing = compute_data_completeness(fields)
        
        # Only price is valid
        assert completeness == 0.25  # 1 of 4
        assert set(missing) == {"bid", "ask", "volume"}
        
        # Build reason
        reason = build_data_incomplete_reason(missing)
        assert "DATA_INCOMPLETE" in reason

    def test_full_orats_data_is_complete(self):
        """Simulates ORATS returning full data."""
        orats_response = {
            "stockPrice": 150.0,
            "bid": 149.5,
            "ask": 150.5,
            "volume": 1000000,
        }
        
        fields = {
            "price": wrap_field_float(orats_response.get("stockPrice"), "price"),
            "bid": wrap_field_float(orats_response.get("bid"), "bid"),
            "ask": wrap_field_float(orats_response.get("ask"), "ask"),
            "volume": wrap_field_int(orats_response.get("volume"), "volume"),
        }
        
        completeness, missing = compute_data_completeness(fields)
        
        assert completeness == 1.0
        assert missing == []
