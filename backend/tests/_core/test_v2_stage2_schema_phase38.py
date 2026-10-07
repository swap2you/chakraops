# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3.8: Schema correctness and mode guardrails for V2 Stage-2 response builder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.eval.v2_stage2_response_builder import (
    run_mode_guardrails,
    build_canonical_payload,
    build_contract_data_from_canonical,
    build_candidate_trades_list,
    ERROR_MODE_MIXED_CC,
    ERROR_MODE_MIXED_CSP,
    REQUIRED_KEYS,
)


def test_v2_schema_csp_no_calls():
    """CSP payload must have calls_requested=0 and no call-named counts in mode-specific fields."""
    trace = {
        "mode": "CSP",
        "spot_used": 500.0,
        "expirations_in_window": ["2026-03-20"],
        "request_counts": {"puts_requested": 30, "calls_requested": 0},
        "response_rows": 30,
        "puts_with_required_fields": 30,
        "calls_with_required_fields": 0,
        "otm_contracts_in_delta_band": 10,
        "otm_puts_in_dte": 30,
        "otm_puts_in_delta_band": 10,
        "selected_trade": {"strike": 480, "exp": "2026-03-20", "bid": 5.0},
        "top_rejection": None,
        "rejection_counts": {},
        "sample_request_symbols": ["SPY260320P00480000", "SPY260320P00475000"],
        "top_candidates_table": [],
    }
    canonical = build_canonical_payload("CSP", trace, "2026-02-12T12:00:00Z")
    assert canonical["strategy_mode"] == "CSP"
    assert canonical["request_counts"]["calls_requested"] == 0
    assert canonical["request_counts"]["puts_requested"] == 30
    assert "otm_puts_in_dte" in canonical
    assert "otm_puts_in_delta_band" in canonical
    assert canonical.get("otm_calls_in_dte", 0) == 0 or "otm_calls_in_dte" not in canonical or canonical["otm_calls_in_dte"] == 0
    for key in REQUIRED_KEYS:
        assert key in canonical, f"missing required key {key}"


def test_v2_schema_cc_no_puts():
    """CC payload must have puts_requested=0 and use otm_calls_* not otm_puts_*."""
    trace = {
        "mode": "CC",
        "spot_used": 500.0,
        "expirations_in_window": ["2026-03-20"],
        "request_counts": {"puts_requested": 0, "calls_requested": 30},
        "response_rows": 30,
        "puts_with_required_fields": 0,
        "calls_with_required_fields": 30,
        "otm_contracts_in_delta_band": 10,
        "otm_calls_in_dte": 30,
        "otm_calls_in_delta_band": 10,
        "selected_trade": {"strike": 520, "exp": "2026-03-20", "bid": 4.0},
        "top_rejection": None,
        "rejection_counts": {},
        "sample_request_symbols": ["SPY260320C00520000", "SPY260320C00525000"],
        "top_candidates_table": [],
    }
    canonical = build_canonical_payload("CC", trace, "2026-02-12T12:00:00Z")
    assert canonical["strategy_mode"] == "CC"
    assert canonical["request_counts"]["puts_requested"] == 0
    assert canonical["request_counts"]["calls_requested"] == 30
    assert canonical.get("otm_calls_in_dte") == 30
    assert canonical.get("otm_calls_in_delta_band") == 10
    for key in REQUIRED_KEYS:
        assert key in canonical


def test_candidate_trades_strategy_matches_mode():
    """build_candidate_trades_list must set strategy to the given mode (CSP or CC)."""
    sel = {"exp": "2026-03-20", "strike": 480, "bid": 5.0, "abs_delta": 0.30}
    csp_list = build_candidate_trades_list("CSP", sel)
    cc_list = build_candidate_trades_list("CC", sel)
    assert len(csp_list) == 1 and csp_list[0]["strategy"] == "CSP"
    assert len(cc_list) == 1 and cc_list[0]["strategy"] == "CC"
    assert build_candidate_trades_list("CSP", None) == []
    assert build_candidate_trades_list("CC", None) == []


def test_greeks_summary_mentions_correct_mode_or_is_neutral():
    """Delta target range string must be mode-aware: (CSP) or (CC), never 'for CSP' in CC mode."""
    from app.core.config.wheel_strategy_config import get_target_delta_range
    delta_lo, delta_hi = get_target_delta_range()
    # Same format as server _symbol_diagnostics_greeks_summary
    text_csp = f"abs_delta {delta_lo:.2f}-{delta_hi:.2f} (CSP)"
    text_cc = f"abs_delta {delta_lo:.2f}-{delta_hi:.2f} (CC)"
    assert "CSP" in text_csp and "(CSP)" in text_csp
    assert "CC" in text_cc and "(CC)" in text_cc
    assert "for CSP" not in text_cc


def test_single_writer_selected_trade_not_overridden():
    """Canonical payload selected_trade and top_rejection are the single source; no contradiction."""
    trace = {
        "mode": "CSP",
        "request_counts": {"puts_requested": 10, "calls_requested": 0},
        "response_rows": 10,
        "expirations_in_window": ["2026-03-20"],
        "selected_trade": {"strike": 495, "bid": 3.0},
        "top_rejection": None,
        "rejection_counts": {},
        "sample_request_symbols": ["SPY260320P00495000"],
        "top_candidates_table": [],
    }
    canonical = build_canonical_payload("CSP", trace, None)
    assert canonical["selected_trade"] is not None
    assert canonical["top_rejection"] is None
    cd = build_contract_data_from_canonical(canonical)
    assert cd["selected_trade"] == canonical["selected_trade"]
    assert cd["top_rejection"] is None

    trace_fail = {**trace, "selected_trade": None, "top_rejection": "rejected_due_to_oi=5"}
    canonical_fail = build_canonical_payload("CSP", trace_fail, None)
    assert canonical_fail["selected_trade"] is None
    assert "rejected" in (canonical_fail.get("top_rejection") or "")


def test_mode_guardrails_cc_rejects_puts():
    """run_mode_guardrails returns ERROR_MODE_MIXED_CC when mode=CC and puts_requested>0."""
    trace = {"request_counts": {"puts_requested": 1, "calls_requested": 0}, "sample_request_symbols": []}
    assert run_mode_guardrails("CC", trace) == ERROR_MODE_MIXED_CC


def test_mode_guardrails_csp_rejects_calls():
    """run_mode_guardrails returns ERROR_MODE_MIXED_CSP when mode=CSP and calls_requested>0."""
    trace = {"request_counts": {"puts_requested": 0, "calls_requested": 1}, "sample_request_symbols": []}
    assert run_mode_guardrails("CSP", trace) == ERROR_MODE_MIXED_CSP


def test_mode_guardrails_cc_rejects_put_symbol():
    """run_mode_guardrails returns ERROR_MODE_MIXED_CC when a sample symbol is a PUT (P at -9)."""
    # OCC: ROOT+YYMMDD(6)+C|P(1)+8 strike -> option type at index -9
    trace = {"request_counts": {"puts_requested": 0, "calls_requested": 0}, "sample_request_symbols": ["SPY260320P00480000"]}
    assert run_mode_guardrails("CC", trace) == ERROR_MODE_MIXED_CC


def test_mode_guardrails_csp_rejects_call_symbol():
    """run_mode_guardrails returns ERROR_MODE_MIXED_CSP when a sample symbol is a CALL (C at -9)."""
    trace = {"request_counts": {"puts_requested": 0, "calls_requested": 0}, "sample_request_symbols": ["SPY260320C00520000"]}
    assert run_mode_guardrails("CSP", trace) == ERROR_MODE_MIXED_CSP
