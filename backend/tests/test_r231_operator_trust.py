# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.1 Operator Trust Fix Pack: contract key normalization, store loader compatibility, delta diagnostics."""

import json
import pytest

from app.core.eval.decision_artifact_v2 import (
    DecisionArtifactV2,
    CandidateRow,
    GateEvaluation,
    SymbolEvalSummary,
    normalize_contract_key,
)


def test_normalize_contract_key_integer_strike():
    """Strike as float 673.0 -> key 673-... (no trailing .0)."""
    assert normalize_contract_key(673.0, "2026-03-20", "PUT") == "673-2026-03-20-PUT"
    assert normalize_contract_key(450, "2026-03-21", "CALL") == "450-2026-03-21-CALL"


def test_normalize_contract_key_none_inputs():
    assert normalize_contract_key(None, "2026-03-20", "PUT") is None
    assert normalize_contract_key(450, None, "PUT") is None
    assert normalize_contract_key(450, "", "PUT") is None


def test_contract_key_normalization_consistent_across_selected_and_candidates():
    """R23.1 Part 1: selected_candidates and candidates_by_symbol share identical contract_key."""
    strike = 673.0
    expiry = "2026-03-20"
    opt_type = "PUT"
    key = normalize_contract_key(strike, expiry, opt_type)
    assert key == "673-2026-03-20-PUT"

    selected = CandidateRow(
        symbol="SPY",
        strategy="CSP",
        expiry=expiry,
        strike=strike,
        delta=-0.25,
        credit_estimate=2.50,
        max_loss=67300,
        contract_key=key,
        option_symbol=None,
    )
    cand_list = [
        CandidateRow(
            symbol="SPY",
            strategy="CSP",
            expiry=expiry,
            strike=strike,
            delta=-0.25,
            credit_estimate=2.50,
            max_loss=67300,
            contract_key=key,
            option_symbol=None,
        ),
    ]
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-02-17T20:00:00Z"},
        symbols=[
            SymbolEvalSummary(
                symbol="SPY",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=65,
                band="B",
                primary_reason=None,
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy="CSP",
                price=673.0,
                expiration=expiry,
                has_candidates=True,
                candidate_count=1,
            )
        ],
        selected_candidates=[selected],
        candidates_by_symbol={"SPY": cand_list},
    )
    out = artifact.to_dict_persist()
    sel = out["selected_candidates"][0]
    by_sym = out["candidates_by_symbol"]["SPY"][0]
    assert sel["contract_key"] == by_sym["contract_key"] == "673-2026-03-20-PUT"
    assert "673.0" not in str(sel["contract_key"])
    assert "673.0" not in str(by_sym["contract_key"])


def test_loader_compat_minimal_persisted_no_reason_no_why_this_trade(tmp_path):
    """R23.1 Part 2: Load artifact from to_dict_persist (gates without reason, candidates without why_this_trade)."""
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
        candidates_by_symbol={
            "WMT": [
                CandidateRow(
                    symbol="WMT",
                    strategy="CSP",
                    expiry="2026-04-18",
                    strike=165.0,
                    delta=-0.28,
                    credit_estimate=1.80,
                    max_loss=16500,
                    contract_key="165-2026-04-18-PUT",
                    option_symbol=None,
                ),
            ],
        },
        gates_by_symbol={
            "WMT": [
                GateEvaluation(name="Stage1", status="PASS", reason=None),
                GateEvaluation(name="DeltaBand", status="FAIL", reason=None),
            ],
        },
        earnings_by_symbol={},
        diagnostics_by_symbol={},
        warnings=[],
    )
    persisted = artifact.to_dict_persist()
    assert "reason" not in persisted["gates_by_symbol"]["WMT"][0]
    assert "why_this_trade" not in persisted["candidates_by_symbol"]["WMT"][0]

    path = tmp_path / "decision_latest.json"
    path.write_text(json.dumps(persisted), encoding="utf-8")

    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        loaded = store.get_latest()
        assert loaded is not None
        assert len(loaded.symbols) == 1
        assert loaded.symbols[0].symbol == "WMT"
        assert len(loaded.gates_by_symbol["WMT"]) == 2
        for g in loaded.gates_by_symbol["WMT"]:
            assert g.reason is None or g.reason is None  # optional
        assert len(loaded.candidates_by_symbol["WMT"]) == 1
        c = loaded.candidates_by_symbol["WMT"][0]
        assert c.contract_key == "165-2026-04-18-PUT"
        assert c.why_this_trade is None
    finally:
        reset_output_dir()


def test_from_dict_normalizes_contract_key_with_trailing_zero():
    """Loader normalizes 673.0-... to 673-... on load."""
    data = {
        "metadata": {"artifact_version": "v2"},
        "symbols": [],
        "selected_candidates": [
            {
                "symbol": "SPY",
                "strategy": "CSP",
                "expiry": "2026-03-20",
                "strike": 673.0,
                "delta": -0.25,
                "credit_estimate": 2.50,
                "max_loss": 67300,
                "contract_key": "673.0-2026-03-20-PUT",
            },
        ],
        "candidates_by_symbol": {},
        "gates_by_symbol": {},
        "earnings_by_symbol": {},
        "warnings": [],
    }
    art = DecisionArtifactV2.from_dict(data)
    assert len(art.selected_candidates) == 1
    assert art.selected_candidates[0].contract_key == "673-2026-03-20-PUT"


def test_delta_diagnostics_best_miss():
    """R23.1 Part 3: _build_delta_diagnostics computes best_delta, miss, direction."""
    from app.api.ui_routes import _build_delta_diagnostics_at_request_time

    sample = [
        {"observed_delta_decimal_abs": 0.15, "strike": 165, "expiry": "2026-04-18", "bid": 1.80, "ask": 2.00},
        {"observed_delta_decimal_abs": 0.45, "strike": 170, "expiry": "2026-04-18", "bid": 1.20, "ask": 1.40},
    ]
    delta_lo, delta_hi = 0.20, 0.40
    out = _build_delta_diagnostics_at_request_time(sample, delta_lo, delta_hi)
    assert out is not None
    assert out["band_min"] == 0.20
    assert out["band_max"] == 0.40
    assert out["direction"] in ("BELOW_BAND", "ABOVE_BAND")
    assert out["best_delta"] == 0.15 or out["best_delta"] == 0.45
    if out["best_delta"] == 0.15:
        assert out["miss"] == pytest.approx(0.05)
        assert out["direction"] == "BELOW_BAND"
    else:
        assert out["miss"] == pytest.approx(0.05)
        assert out["direction"] == "ABOVE_BAND"
    assert "best_candidate" in out
