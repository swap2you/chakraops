# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Delta unit: canonical decimal; normalize percent at ingestion; Stage-2 uses decimal thresholds."""

from __future__ import annotations

import pytest

from app.core.options.orats_chain_pipeline import _delta_to_decimal


def test_delta_to_decimal_already_decimal():
    """Raw 0.32 stays 0.32 (decimal)."""
    assert _delta_to_decimal(0.32) == 0.32
    assert _delta_to_decimal(-0.32) == -0.32


def test_delta_to_decimal_percent_normalized():
    """Raw 32 (percent) normalized to 0.32."""
    assert _delta_to_decimal(32) == 0.32
    assert _delta_to_decimal(-32) == -0.32


def test_delta_to_decimal_none_invalid():
    """None or invalid returns None."""
    assert _delta_to_decimal(None) is None
    assert _delta_to_decimal("") is None


def test_delta_gate_pass_when_decimal_in_range():
    """Stage-2 delta gate: 0.32 in [0.15, 0.35] passes (decimal comparison)."""
    from app.core.eval.staged_evaluator import _delta_magnitude
    from app.core.models.data_quality import FieldValue, DataQuality
    from app.core.options.chain_provider import OptionContract, OptionType
    from datetime import date, timedelta

    exp = date.today() + timedelta(days=40)
    put = OptionContract(
        symbol="HD",
        expiration=exp,
        strike=400.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        delta=FieldValue(0.32, DataQuality.VALID, "", "delta"),
        open_interest=FieldValue(500, DataQuality.VALID, "", "open_interest"),
        dte=40,
    )
    mag = _delta_magnitude(put)
    assert mag is not None
    delta_lo, delta_hi = 0.15, 0.35
    assert delta_lo <= mag <= delta_hi, f"Delta {mag} should be in [{delta_lo}, {delta_hi}]"


# Regression: gate uses abs(delta) for band [0.20, 0.40]; no signed-delta rejection when abs in range.
DELTA_LO, DELTA_HI = 0.20, 0.40


def test_csp_put_delta_negative_031_passes_abs_band():
    """CSP put delta = -0.31 must PASS delta band [0.20, 0.40] when using abs(delta)."""
    from app.core.eval.staged_evaluator import _delta_magnitude
    from app.core.models.data_quality import FieldValue, DataQuality
    from app.core.options.chain_provider import OptionContract, OptionType
    from datetime import date, timedelta

    exp = date.today() + timedelta(days=40)
    put = OptionContract(
        symbol="HD",
        expiration=exp,
        strike=400.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        delta=FieldValue(-0.31, DataQuality.VALID, "", "delta"),
        open_interest=FieldValue(500, DataQuality.VALID, "", "open_interest"),
        dte=40,
    )
    mag = _delta_magnitude(put)
    assert mag is not None
    assert mag == 0.31
    assert DELTA_LO <= mag <= DELTA_HI, f"abs(delta) {mag} should be in [{DELTA_LO}, {DELTA_HI}]"


def test_call_delta_positive_031_passes_abs_band():
    """Call delta = +0.31 must PASS same band [0.20, 0.40] (magnitude check)."""
    from app.core.eval.staged_evaluator import _delta_magnitude
    from app.core.models.data_quality import FieldValue, DataQuality
    from app.core.options.chain_provider import OptionContract, OptionType
    from datetime import date, timedelta

    exp = date.today() + timedelta(days=40)
    call = OptionContract(
        symbol="HD",
        expiration=exp,
        strike=400.0,
        option_type=OptionType.CALL,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        delta=FieldValue(0.31, DataQuality.VALID, "", "delta"),
        open_interest=FieldValue(500, DataQuality.VALID, "", "open_interest"),
        dte=40,
    )
    mag = _delta_magnitude(call)
    assert mag is not None
    assert mag == 0.31
    assert DELTA_LO <= mag <= DELTA_HI


def test_put_delta_negative_045_fails_abs_band():
    """Put delta = -0.45 must FAIL for band [0.20, 0.40]."""
    from app.core.eval.staged_evaluator import _delta_magnitude
    from app.core.models.data_quality import FieldValue, DataQuality
    from app.core.options.chain_provider import OptionContract, OptionType
    from datetime import date, timedelta

    exp = date.today() + timedelta(days=40)
    put = OptionContract(
        symbol="HD",
        expiration=exp,
        strike=400.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        delta=FieldValue(-0.45, DataQuality.VALID, "", "delta"),
        open_interest=FieldValue(500, DataQuality.VALID, "", "open_interest"),
        dte=40,
    )
    mag = _delta_magnitude(put)
    assert mag is not None
    assert mag == 0.45
    assert not (DELTA_LO <= mag <= DELTA_HI), f"abs(delta) {mag} must fail band [{DELTA_LO}, {DELTA_HI}]"


def test_raw_32_normalized_then_abs_check_passes():
    """Raw 32 (percent) -> 0.32 via _delta_to_decimal; then abs check passes for [0.20, 0.40]."""
    d = _delta_to_decimal(32)
    assert d == 0.32
    d_abs = abs(d)
    assert DELTA_LO <= d_abs <= DELTA_HI
