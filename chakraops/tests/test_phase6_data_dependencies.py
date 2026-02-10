# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6: Data dependency enforcement — required/optional/stale, data_sufficiency, BLOCKED."""

from __future__ import annotations

import pytest

from app.core.symbols.data_dependencies import (
    compute_required_missing,
    compute_optional_missing,
    compute_required_stale,
    dependency_status,
    get_data_as_of,
    compute_dependency_lists,
    REQUIRED_EVALUATION_FIELDS,
    OPTIONAL_EVALUATION_FIELDS,
)
from app.core.symbols.data_sufficiency import derive_data_sufficiency_with_dependencies
from app.core.ranking.service import rank_opportunities


def test_required_missing_blocks_when_required_missing() -> None:
    """Required data missing → BLOCKED in ranking (Phase 8E: only for EQUITY where bid/ask are required)."""
    from unittest.mock import patch
    from app.core.symbols.instrument_type import InstrumentType
    symbols = [{
        "symbol": "MISS",
        "verdict": "ELIGIBLE",
        "score": 80,
        "price": 100.0,
        "bid": None,
        "ask": 100.5,
        "volume": 1000,
        "iv_rank": 40.0,
        "quote_date": "2025-02-01",
        "liquidity_ok": True,
        "position_open": False,
        "candidate_trades": [{"strategy": "CSP", "strike": 90, "delta": -0.20}],
        "capital_hint": {"band": "A"},
        "score_breakdown": {"composite_score": 80},
        "primary_reason": "ok",
        "data_completeness": 0.8,
        "stage_reached": "STAGE2_CHAIN",
        "rank_reasons": {"reasons": [], "penalty": None},
    }]
    # Phase 8E: MISS must be EQUITY so bid/ask are required; otherwise INDEX would not require bid
    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        ranked = rank_opportunities(symbols, include_blocked=True, limit=10)
    assert len(ranked) == 1
    assert ranked[0]["risk_status"] == "BLOCKED"
    assert "Required data missing" in (ranked[0].get("risk_reasons") or [""])[0]
    assert "bid" in (ranked[0].get("required_data_missing") or [])


def test_required_missing_empty_allows_ok() -> None:
    """When all required fields present, risk_status not BLOCKED by data."""
    symbols = [{
        "symbol": "OK",
        "verdict": "ELIGIBLE",
        "score": 80,
        "price": 100.0,
        "bid": 99.5,
        "ask": 100.5,
        "volume": 1000,
        "iv_rank": 40.0,
        "quote_date": "2025-02-01",
        "liquidity_ok": True,
        "position_open": False,
        "candidate_trades": [{"strategy": "CSP", "strike": 90, "delta": -0.20}],
        "capital_hint": {"band": "A"},
        "score_breakdown": {"composite_score": 80},
        "primary_reason": "ok",
        "data_completeness": 0.95,
        "stage_reached": "STAGE2_CHAIN",
        "rank_reasons": {"reasons": [], "penalty": None},
    }]
    ranked = rank_opportunities(symbols, include_blocked=False, limit=10)
    assert len(ranked) == 1
    assert ranked[0].get("risk_status") != "BLOCKED" or "Required data missing" not in str(ranked[0].get("risk_reasons")) 


def test_dependency_status_fail_when_required_missing() -> None:
    """dependency_status returns FAIL when required_data_missing non-empty."""
    assert dependency_status(["price"], [], []) == "FAIL"
    assert dependency_status(["iv_rank", "bid"], [], []) == "FAIL"


def test_dependency_status_warn_when_stale_or_optional_missing() -> None:
    """WARN when required_data_stale or optional_data_missing (and no required missing)."""
    assert dependency_status([], ["price"], []) == "WARN"
    assert dependency_status([], [], ["some_optional"]) == "WARN"


def test_dependency_status_pass_when_all_clear() -> None:
    """PASS only when required_data_missing and required_data_stale empty."""
    assert dependency_status([], [], []) == "PASS"


def test_compute_required_missing_delta_for_eligible() -> None:
    """When ELIGIBLE and candidate has no delta, delta is required missing."""
    sym = {
        "symbol": "X",
        "verdict": "ELIGIBLE",
        "price": 100,
        "bid": 99,
        "ask": 101,
        "volume": 1000,
        "iv_rank": 50.0,
        "candidate_trades": [{"strategy": "CSP", "strike": 90}],
    }
    missing = compute_required_missing(sym)
    assert "delta" in missing


def test_compute_optional_missing_no_avg_volume() -> None:
    """avg_volume is not in OPTIONAL_EVALUATION_FIELDS (does not exist in ORATS per DATA_REQUIREMENTS)."""
    sym = {"symbol": "X", "price": 100, "bid": 99, "ask": 101, "volume": 1000, "iv_rank": 50.0}
    optional = compute_optional_missing(sym)
    assert "avg_volume" not in optional


def test_data_sufficiency_no_pass_when_required_missing() -> None:
    """derive_data_sufficiency_with_dependencies never returns PASS when required_data_missing."""
    # Symbol not in run → FAIL with required_data_missing
    out = derive_data_sufficiency_with_dependencies("NONEXISTENT_SYMBOL_XYZ")
    assert out["status"] == "FAIL"
    assert (out.get("required_data_missing") or []) != []
    assert out["required_data_missing"]  # non-empty
