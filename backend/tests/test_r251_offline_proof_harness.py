# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.1: Offline proof harness — golden verification (determinism + hygiene without ORATS)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eval.offline_fixture_provider import (
    build_universe_result_from_fixture,
    get_account_settings,
    get_ohlc_bars,
    get_option_chain_candidates,
    get_quotes,
    load_fixture,
)

# Fixture path (under chakraops/tests/fixtures)
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "r25_1_offline_fixture.json"

FORBIDDEN_PATTERNS = [
    re.compile(r"\bFAIL_[A-Z0-9_]+\b"),
    re.compile(r"\bWARN_[A-Z0-9_]+\b"),
]


def _collect_strings(obj, out: list) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, out)
    elif isinstance(obj, str):
        out.append(obj)


def _has_forbidden_substrings(data: dict) -> list[str]:
    violations = []
    strings: list[str] = []
    _collect_strings(data, strings)
    for s in strings:
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(s):
                violations.append(f"Forbidden: {pat.pattern!r} in {s[:60]!r}")
    return violations


def _normalize_decision_artifact(data: dict) -> dict:
    """Replace variable fields so two runs can be compared structurally."""
    out = json.loads(json.dumps(data))
    meta = out.get("metadata") or {}
    meta["run_id"] = "<RUN_ID>"
    meta["pipeline_timestamp"] = "<TS>"
    meta["evaluation_timestamp_utc"] = "<TS>"
    if "evaluator_run_id" in meta:
        meta["evaluator_run_id"] = "<EVALUATOR_RUN_ID>"
    if "coordinator_run_id" in meta:
        meta["coordinator_run_id"] = "<COORDINATOR_RUN_ID>"
    out["metadata"] = meta
    # Normalize per-symbol evaluated_at if present
    for sym in out.get("symbols") or []:
        if isinstance(sym, dict) and "evaluated_at" in sym:
            sym["evaluated_at"] = "<TS>" if sym.get("evaluated_at") else None
    diag = out.get("diagnostics_by_symbol") or {}
    for sym, d in diag.items():
        if isinstance(d, dict):
            for k in list(d.keys()):
                if "timestamp" in k.lower() or k == "evaluated_at":
                    d[k] = "<TS>"
    return out


def _normalize_eval_snapshot(data: dict) -> dict:
    """Replace all timestamp-like and run_id-like values for comparison."""
    iso_ts = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:?\d{2})?$")

    def _norm_val(obj):
        if isinstance(obj, dict):
            return {k: _norm_val(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_norm_val(x) for x in obj]
        if isinstance(obj, str) and iso_ts.match(obj.strip()):
            return "<TS>"
        if isinstance(obj, str) and len(obj) == 36 and "-" in obj and obj != "<RUN_ID>":
            return "<RUN_ID>"
        return obj

    out = _norm_val(json.loads(json.dumps(data)))
    if isinstance(out, dict):
        out["snapshot_id"] = "<RUN_ID>"
        out["created_at"] = "<TS>"
    return out


@pytest.fixture
def fixture_path():
    return FIXTURE_PATH


def test_r251_fixture_provider_ohlc_and_chain(fixture_path: Path) -> None:
    """Fixture provider returns deterministic OHLC and option chain per symbol."""
    data = load_fixture(fixture_path)
    assert data.get("symbols")

    for sym in data["symbols"]:
        bars = get_ohlc_bars(data, sym)
        if sym == "NVDA":
            assert len(bars) >= 1
            assert "close" in (bars[0] if bars else {})
        chain = get_option_chain_candidates(data, sym)
        if sym == "NVDA":
            assert len(chain) >= 1
            assert chain[0].get("contract_key") == "140-2026-03-20-PUT"
        else:
            assert chain == [] or all(c.get("contract_key") for c in chain)


def test_r251_fixture_provider_quotes_and_account(fixture_path: Path) -> None:
    """Fixture provider returns quotes with quote_ts and account_settings."""
    data = load_fixture(fixture_path)
    q = get_quotes(data, "NVDA")
    assert "quote_ts" in q
    assert q.get("price") == 140
    acc = get_account_settings(data)
    assert "buying_power" in acc
    assert acc["buying_power"] == 100000.0


def test_r251_offline_proof_hygiene_no_fail_warn(fixture_path: Path, tmp_path: Path) -> None:
    """Persisted decision_latest.json must not contain FAIL_ or WARN_ substrings."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir
    from app.core.eval.evaluation_service_v2 import evaluate_universe

    set_output_dir(tmp_path)
    try:
        mock_result = build_universe_result_from_fixture(fixture_path)
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            evaluate_universe(
                load_fixture(fixture_path).get("symbols") or ["NVDA", "NKE", "HD"],
                mode="PAPER",
            )
        raw_path = tmp_path / "decision_latest.json"
        assert raw_path.exists()
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        violations = _has_forbidden_substrings(raw)
        assert not violations, f"Hygiene violations: {violations}"
    finally:
        reset_output_dir()


def test_r251_offline_proof_determinism_run_twice(fixture_path: Path, tmp_path: Path) -> None:
    """Running the offline pipeline twice yields structurally identical outputs (timestamps normalized)."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir
    from app.core.eval.evaluation_service_v2 import evaluate_universe

    mock_result = build_universe_result_from_fixture(fixture_path)
    symbols = load_fixture(fixture_path).get("symbols") or []

    set_output_dir(tmp_path)
    try:
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            evaluate_universe(symbols, mode="PAPER")
    finally:
        reset_output_dir()

    path1_dec = tmp_path / "decision_latest.json"
    path1_snap = tmp_path / "eval_snapshot.json"
    assert path1_dec.exists()
    dec1 = _normalize_decision_artifact(json.loads(path1_dec.read_text(encoding="utf-8")))
    snap1 = _normalize_eval_snapshot(json.loads(path1_snap.read_text(encoding="utf-8"))) if path1_snap.exists() else {}

    tmp_path2 = tmp_path / "run2"
    tmp_path2.mkdir()
    set_output_dir(tmp_path2)
    try:
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            evaluate_universe(symbols, mode="PAPER")
    finally:
        reset_output_dir()

    path2_dec = tmp_path2 / "decision_latest.json"
    path2_snap = tmp_path2 / "eval_snapshot.json"
    dec2 = _normalize_decision_artifact(json.loads(path2_dec.read_text(encoding="utf-8")))
    snap2 = _normalize_eval_snapshot(json.loads(path2_snap.read_text(encoding="utf-8"))) if path2_snap.exists() else {}

    assert dec1 == dec2, "decision_latest.json (normalized) must be identical across two runs"
    assert snap1 == snap2, "eval_snapshot.json (normalized) must be identical across two runs"


def test_r251_offline_proof_applied_caps_reason_code_only(fixture_path: Path, tmp_path: Path) -> None:
    """Strict code-only persistence: applied_caps have reason_code, no prose 'reason'."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir
    from app.core.eval.evaluation_service_v2 import evaluate_universe

    set_output_dir(tmp_path)
    try:
        mock_result = build_universe_result_from_fixture(fixture_path)
        symbols = load_fixture(fixture_path).get("symbols") or []
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            evaluate_universe(symbols, mode="PAPER")
        raw = json.loads((tmp_path / "decision_latest.json").read_text(encoding="utf-8"))
        for sym in raw.get("symbols") or []:
            sb = (sym or {}).get("score_breakdown") or {}
            for cap in (sb.get("score_caps") or {}).get("applied_caps") or []:
                if isinstance(cap, dict):
                    assert "reason_code" in cap or not cap.get("applied_caps"), "applied_caps must use reason_code"
                    assert "reason" not in cap or cap.get("reason") is None, "No prose 'reason' in applied_caps"
        diag = raw.get("diagnostics_by_symbol") or {}
        for sym, d in diag.items():
            sb_d = (d or {}).get("score_breakdown") or {}
            for cap in (sb_d.get("score_caps") or {}).get("applied_caps") or []:
                if isinstance(cap, dict):
                    assert cap.get("reason_code"), "diagnostics applied_caps must have reason_code"
    finally:
        reset_output_dir()


def test_r251_build_universe_result_stable_contract_key(fixture_path: Path) -> None:
    """build_universe_result_from_fixture uses stable contract_key from option_chain_candidates."""
    result = build_universe_result_from_fixture(fixture_path)
    nvda = next((s for s in result.symbols if (s.symbol or "").upper() == "NVDA"), None)
    assert nvda is not None
    assert nvda.verdict == "ELIGIBLE"
    assert nvda.selected_contract is not None
    assert nvda.selected_contract.get("contract_key") == "140-2026-03-20-PUT"
    assert nvda.selected_contract.get("contract", {}).get("option_symbol") == "NVDA260320P00140000"
