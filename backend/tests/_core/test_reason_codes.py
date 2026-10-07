# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Explainable reasons: code → plain-English with metrics."""

from __future__ import annotations

import pytest

from app.core.eval.reason_codes import explain_reasons, format_reason_for_display


def test_delta_rejection_with_sample():
    """rejected_due_to_delta with sample yields message with abs(delta) and range (gate uses abs)."""
    top = {
        "sample_rejected_due_to_delta": [
            {"observed_delta_decimal_abs": 0.32, "observed_delta_pct_abs": 32, "target_range_decimal": "0.15–0.35"},
        ],
    }
    out = explain_reasons("rejected_due_to_delta=32", None, None, top)
    assert len(out) >= 1
    assert out[0]["code"] == "rejected_due_to_delta"
    assert "abs(delta)" in out[0]["message"].lower()
    assert "0.32" in out[0]["message"]
    assert "0.15" in out[0]["message"] or "0.15–0.35" in out[0]["message"]


def test_delta_rejection_no_sample_generic_message():
    """When primary has rejected_due_to_delta but no sample, message is generic (N may be count not delta)."""
    out = explain_reasons("No contract passed filters (rejected_due_to_delta=32)", None, None, None)
    assert len(out) >= 1
    assert out[0]["code"] == "rejected_due_to_delta"
    assert "abs(delta)" in out[0]["message"].lower()
    assert "0.20" in out[0]["message"]


def test_data_incomplete():
    """DATA_INCOMPLETE or required missing → message with missing list."""
    sel = {"required_data_missing": ["resistance_level", "ATR14"]}
    out = explain_reasons("DATA_INCOMPLETE", sel, None, None)
    assert len(out) >= 1
    assert out[0]["code"] == "DATA_INCOMPLETE"
    assert "resistance_level" in out[0]["message"]
    assert "ATR14" in out[0]["message"]


def test_other_fallback():
    """Unknown primary_reason → OTHER with safe message (never raw codes)."""
    out = explain_reasons("SOME_UNKNOWN_CODE", None, None, None)
    assert len(out) == 1
    assert out[0]["code"] == "OTHER"
    assert "See diagnostics" in out[0]["message"]
    assert "SOME_UNKNOWN_CODE" not in out[0]["message"]


def test_format_reason_for_display_rejected_due_to_delta():
    """format_reason_for_display converts rejected_due_to_delta=N to rejected_count (never delta)."""
    assert "rejected_count=32" in format_reason_for_display("rejected_due_to_delta=32")
    assert "delta=32" not in format_reason_for_display("rejected_due_to_delta=32")


def test_persisted_diagnostics_no_reasons_explained():
    """SymbolDiagnosticsDetails.to_dict() does not persist reasons_explained (code-only)."""
    from app.core.eval.decision_artifact_v2 import SymbolDiagnosticsDetails

    d = SymbolDiagnosticsDetails(
        technicals={},
        exit_plan={},
        risk_flags={},
        explanation={},
        stock={},
        symbol_eligibility={},
        liquidity={},
        reasons_explained=[{"code": "x", "message": "raw text"}],
    )
    out = d.to_dict()
    assert "reasons_explained" not in out


def test_rejected_due_to_delta_shows_count_not_delta():
    """rejected_due_to_delta=32 → message shows rejected_count, never delta=32."""
    out = explain_reasons("No contract passed (rejected_due_to_delta=32)", None, None, None)
    assert len(out) >= 1
    assert out[0]["code"] == "rejected_due_to_delta"
    assert "rejected_count=32" in out[0]["message"]
    assert "delta=32" not in out[0]["message"]
