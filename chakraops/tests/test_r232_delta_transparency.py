# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.2: Delta transparency, gate_code persistence, delta override boundaries."""

import json
import pytest

from app.core.eval.decision_artifact_v2 import (
    DecisionArtifactV2,
    GateEvaluation,
    SymbolEvalSummary,
    gate_name_to_code,
    gate_code_to_label,
)


def test_gate_name_to_code():
    assert gate_name_to_code("Stock Quality (Stage 1)") == "STOCK_QUALITY_STAGE1"
    assert gate_name_to_code("Options Liquidity (Stage 2)") == "OPTIONS_LIQUIDITY_STAGE2"
    assert gate_name_to_code("DeltaBand") == "DELTA_BAND"
    assert gate_name_to_code("ORATS Summary") == "ORATS_SUMMARY"
    assert gate_name_to_code("Unknown Gate Name") == "UNKNOWN_GATE"
    assert gate_name_to_code("STOCK_QUALITY_STAGE1") == "STOCK_QUALITY_STAGE1"


def test_gate_code_to_label():
    assert gate_code_to_label("STOCK_QUALITY_STAGE1") == "Stock quality (Stage 1)"
    assert gate_code_to_label("OPTIONS_LIQUIDITY_STAGE2") == "Options liquidity (Stage 2)"
    assert gate_code_to_label("UNKNOWN_GATE") == "Unknown Gate"


def test_persisted_gates_contain_gate_code_no_name(tmp_path):
    """R23.2: Persisted gates have gate_code (regex ^[A-Z0-9_]+$), no 'name' field."""
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-02-17T20:00:00Z"},
        symbols=[
            SymbolEvalSummary(
                symbol="WMT",
                verdict="HOLD",
                final_verdict="HOLD",
                score=50,
                band="C",
                primary_reason=None,
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="FAIL",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy=None,
                price=170.0,
                expiration=None,
                has_candidates=False,
                candidate_count=0,
            )
        ],
        selected_candidates=[],
        candidates_by_symbol={},
        gates_by_symbol={
            "WMT": [
                GateEvaluation(name="Stock Quality (Stage 1)", status="PASS", reason=None, gate_code="STOCK_QUALITY_STAGE1"),
                GateEvaluation(name="Options Liquidity (Stage 2)", status="FAIL", reason=None, gate_code="OPTIONS_LIQUIDITY_STAGE2"),
            ],
        },
        earnings_by_symbol={},
        diagnostics_by_symbol={},
        warnings=[],
    )
    out = artifact.to_dict_persist()
    gates = out["gates_by_symbol"]["WMT"]
    import re
    code_re = re.compile(r"^[A-Z0-9_]+$")
    for g in gates:
        assert "gate_code" in g
        assert code_re.match(g["gate_code"]), f"gate_code must match ^[A-Z0-9_]+$: {g['gate_code']}"
        assert "name" not in g
        assert "reason" not in g
        assert "status" in g


def test_delta_diagnostics_builder_direction_codes():
    """R23.2: delta_diagnostics uses BELOW_BAND/ABOVE_BAND (code-only)."""
    from app.api.ui_routes import _build_delta_diagnostics_at_request_time

    sample_below = [{"observed_delta_decimal_abs": 0.18, "strike": 165, "expiry": "2026-04-18", "bid": 1.80, "ask": 2.00}]
    sample_above = [{"observed_delta_decimal_abs": 0.42, "strike": 170, "expiry": "2026-04-18", "bid": 1.20, "ask": 1.40}]
    out_below = _build_delta_diagnostics_at_request_time(sample_below, 0.20, 0.40)
    out_above = _build_delta_diagnostics_at_request_time(sample_above, 0.20, 0.40)
    assert out_below is not None
    assert out_below["direction"] == "BELOW_BAND"
    assert out_above is not None
    assert out_above["direction"] == "ABOVE_BAND"


def test_delta_override_boundaries(tmp_path):
    """R23.2: Override within allowed widen succeeds; exceeding max_widen rejected."""
    from app.core.config.delta_overrides import (
        set_delta_overrides_path,
        reset_delta_overrides_path,
        save_delta_override,
        delete_delta_override,
        load_delta_overrides,
    )

    override_file = tmp_path / "data" / "delta_overrides.json"
    override_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        set_delta_overrides_path(override_file.parent / "delta_overrides.json")
        # Within max_widen (0.05): e.g. 0.25, 0.35 -> 0.22, 0.38
        ok, err = save_delta_override("WMT", 0.22, 0.38, 0.05, 0.25, 0.35)
        assert ok, err
        overrides = load_delta_overrides()
        assert "WMT" in overrides
        assert overrides["WMT"]["delta_lo"] == 0.22
        assert overrides["WMT"]["delta_hi"] == 0.38

        # Exceed max_widen: 0.15, 0.45 (lo too low, hi too high)
        ok2, err2 = save_delta_override("WMT", 0.15, 0.45, 0.05, 0.25, 0.35)
        assert not ok2
        assert err2

        # Invalid: delta_lo > delta_hi
        ok3, err3 = save_delta_override("WMT", 0.35, 0.25, 0.05, 0.25, 0.35)
        assert not ok3

        delete_delta_override("WMT")
        overrides2 = load_delta_overrides()
        assert "WMT" not in overrides2
    finally:
        reset_delta_overrides_path()


def test_overrides_not_in_decision_json(tmp_path):
    """R23.2: Delta overrides do not appear in decision_latest.json (only influence evaluation)."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    artifact = {
        "metadata": {"artifact_version": "v2", "pipeline_timestamp": "2026-02-17T20:00:00Z"},
        "symbols": [{"symbol": "WMT", "verdict": "HOLD", "final_verdict": "HOLD", "score": 50, "band": "C", "primary_reason": None, "stage_status": "RUN", "stage1_status": "PASS", "stage2_status": "FAIL", "provider_status": "OK", "data_freshness": None, "evaluated_at": None, "strategy": None, "price": 170.0, "expiration": None, "has_candidates": False, "candidate_count": 0}],
        "selected_candidates": [],
        "candidates_by_symbol": {},
        "gates_by_symbol": {"WMT": [{"gate_code": "STOCK_QUALITY_STAGE1", "status": "PASS"}, {"gate_code": "OPTIONS_LIQUIDITY_STAGE2", "status": "FAIL"}]},
        "earnings_by_symbol": {},
        "warnings": [],
    }
    (tmp_path / "decision_latest.json").write_text(json.dumps(artifact), encoding="utf-8")
    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        loaded = store.get_latest()
        assert loaded is not None
        raw = (tmp_path / "decision_latest.json").read_text(encoding="utf-8")
        assert "delta_override" not in raw
        assert "delta_overrides" not in raw
    finally:
        reset_output_dir()
