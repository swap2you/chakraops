# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.1 — canonical reason-code registry tests."""

from __future__ import annotations

import pytest

from app.core.decision_engine import reason_registry as R


# Verified canonical decision-engine codes (from the emission audit).
CANONICAL_CODES = [
    "STALE_PRICE", "STALE_OPTIONS_CHAIN", "MISSING_PRICE", "MISSING_OPTIONS_CHAIN",
    "MISSING_CONTRACT", "MISSING_STRIKE", "MISSING_PREMIUM", "MISSING_DELTA", "MISSING_DTE",
    "LIQUIDITY_DATA_MISSING", "LOW_OPEN_INTEREST", "LOW_VOLUME", "WIDE_SPREAD",
    "INSUFFICIENT_SHARES", "SECTOR_DATA_UNAVAILABLE", "SECTOR_BLOCKED_PENDING_DATA",
    "SECTOR_EXPOSURE_LIMIT_REACHED", "INSUFFICIENT_CASH",
    "DELTA_OUT_OF_RANGE", "DTE_OUT_OF_RANGE", "BELOW_RETURN_THRESHOLD", "ZERO_SIZE",
    "DELTA_IN_RANGE", "DTE_IN_RANGE", "MEETS_RETURN_THRESHOLD", "SHARE_BUY_CANDIDATE",
    "EARNINGS_DATA_UNAVAILABLE", "IV_RANK_UNAVAILABLE", "LIQUIDITY_VALIDATED_UPSTREAM",
]

SAFETY_CRITICAL = [
    "STALE_PRICE", "STALE_OPTIONS_CHAIN", "MISSING_PRICE", "MISSING_OPTIONS_CHAIN",
    "MISSING_CONTRACT", "MISSING_STRIKE", "MISSING_PREMIUM", "MISSING_DELTA", "MISSING_DTE",
    "LIQUIDITY_DATA_MISSING", "LOW_OPEN_INTEREST", "LOW_VOLUME", "WIDE_SPREAD",
    "INSUFFICIENT_SHARES", "SECTOR_DATA_UNAVAILABLE", "SECTOR_BLOCKED_PENDING_DATA",
    "SECTOR_EXPOSURE_LIMIT_REACHED", "INSUFFICIENT_CASH",
]

TEMPORARY = ["DELTA_OUT_OF_RANGE", "DTE_OUT_OF_RANGE", "BELOW_RETURN_THRESHOLD", "ZERO_SIZE"]


@pytest.mark.parametrize("code", CANONICAL_CODES)
def test_every_canonical_code_resolves(code):
    rc = R.resolve(code)
    assert rc.code == code
    assert rc.title and rc.explanation
    assert rc.severity in (R.SEV_HARD, R.SEV_SOFT, R.SEV_INFO)
    assert rc.klass in (R.KLASS_SAFETY_CRITICAL, R.KLASS_TEMPORARY, R.KLASS_INFORMATIONAL)


@pytest.mark.parametrize("code", SAFETY_CRITICAL)
def test_hard_gates_are_safety_critical(code):
    rc = R.resolve(code)
    assert rc.is_safety_critical is True
    assert rc.severity == R.SEV_HARD
    assert R.is_safety_critical(code) is True


@pytest.mark.parametrize("code", TEMPORARY)
def test_soft_gates_are_temporary(code):
    rc = R.resolve(code)
    assert rc.is_temporary is True
    assert R.is_safety_critical(code) is False


@pytest.mark.parametrize("raw,base", [
    ("EARNINGS_BLACKOUT_3D", "EARNINGS_BLACKOUT"),
    ("EARNINGS_BLACKOUT_7D", "EARNINGS_BLACKOUT"),
    ("REGIME_EXCLUDED_BEAR", "REGIME_EXCLUDED"),
    ("REGIME_EXCLUDED_UNKNOWN", "REGIME_EXCLUDED"),
    ("UNKNOWN_STRATEGY_FOO", "UNKNOWN_STRATEGY"),
])
def test_interpolated_families_resolve_by_prefix(raw, base):
    rc = R.resolve(raw)
    assert rc.code == base


def test_earnings_and_regime_families_are_safety_critical():
    assert R.is_safety_critical("EARNINGS_BLACKOUT_3D") is True
    assert R.is_safety_critical("REGIME_EXCLUDED_BEAR") is True


def test_unknown_code_maps_to_safe_generic():
    rc = R.resolve("TOTALLY_UNKNOWN_CODE")
    assert rc.category == "OTHER"
    assert rc.klass == R.KLASS_INFORMATIONAL
    assert "FAIL_" not in rc.title and "WARN_" not in rc.title


def test_resolve_strips_legacy_prefixes_and_never_leaks():
    rc = R.resolve("FAIL_DELTA_OUT_OF_RANGE")
    assert rc.code == "DELTA_OUT_OF_RANGE"
    rc2 = R.resolve("WARN_SOMETHING_ODD")
    assert "WARN_" not in rc2.title and "WARN_" not in rc2.explanation


def test_resolve_handles_none_and_empty():
    assert R.resolve(None).category == "OTHER"
    assert R.resolve("").category == "OTHER"
    assert R.resolve(123).category == "OTHER"  # type: ignore[arg-type]


def test_registry_entries_have_units_for_numeric_codes():
    for code in ("LOW_OPEN_INTEREST", "LOW_VOLUME", "WIDE_SPREAD",
                 "DELTA_OUT_OF_RANGE", "DTE_OUT_OF_RANGE", "BELOW_RETURN_THRESHOLD"):
        rc = R.resolve(code)
        assert rc.unit is not None
        assert rc.measured_field and rc.threshold_field


def test_all_codes_and_to_dict():
    codes = R.all_codes()
    assert "DELTA_OUT_OF_RANGE" in codes
    d = R.resolve("DELTA_OUT_OF_RANGE").to_dict()
    assert d["code"] == "DELTA_OUT_OF_RANGE" and d["klass"] == R.KLASS_TEMPORARY
