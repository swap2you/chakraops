# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.8: Offline proof harness — run fixture-driven eval, assert hygiene and golden determinism."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_decision_artifact_hygiene_r227 import (
    FORBIDDEN_PATTERNS,
    FORBIDDEN_PROSE_SUBSTRINGS,
    STRICT_CODE_RE,
    _check_applied_caps_reason_code_only,
    _check_forbidden_keys,
    _check_forbidden_strings,
    _collect_strings,
)


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "r22_8_offline_proof_fixture.json"


def _run_offline_eval(fixture_path: Path, output_dir: Path):
    """Run offline proof code path: fixture -> mock staged result -> evaluate_universe -> store write."""
    from app.core.eval.offline_fixture_provider import build_universe_result_from_fixture, load_fixture
    from app.core.eval.evaluation_service_v2 import evaluate_universe
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir

    symbols = load_fixture(fixture_path).get("symbols") or []
    assert symbols, "Fixture must define symbols"
    set_output_dir(output_dir)
    try:
        mock_result = build_universe_result_from_fixture(fixture_path)
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            return evaluate_universe(symbols, mode="LIVE")
    finally:
        reset_output_dir()


def test_offline_proof_produces_artifact_and_passes_hygiene(tmp_path: Path) -> None:
    """R22.8: Run offline eval, load produced decision_latest.json, assert no prose and applied_caps have reason_code."""
    _run_offline_eval(FIXTURE_PATH, tmp_path)
    decision_file = tmp_path / "decision_latest.json"
    assert decision_file.exists(), "Store must write decision_latest.json"
    raw = json.loads(decision_file.read_text(encoding="utf-8"))

    violations_keys = _check_forbidden_keys(raw)
    violations_str = _check_forbidden_strings(raw)
    violations_caps = _check_applied_caps_reason_code_only(raw)
    assert not violations_keys, f"Forbidden keys: {violations_keys}"
    assert not violations_str, f"Forbidden strings/prose: {violations_str}"
    assert not violations_caps, f"applied_caps must have reason_code only: {violations_caps}"


def test_offline_proof_no_fail_warn_patterns(tmp_path: Path) -> None:
    """R22.8: Persisted artifact must not contain FAIL_* or WARN_* in any string value."""
    _run_offline_eval(FIXTURE_PATH, tmp_path)
    raw = json.loads((tmp_path / "decision_latest.json").read_text(encoding="utf-8"))
    strings: list = []
    _collect_strings(raw, strings)
    for s in strings:
        for pat in FORBIDDEN_PATTERNS:
            assert not pat.search(s), f"Persisted value must not match {pat.pattern!r}: {s[:80]!r}"


def test_offline_proof_no_prose_substrings(tmp_path: Path) -> None:
    """R22.8: Persisted artifact must not contain known prose substrings."""
    _run_offline_eval(FIXTURE_PATH, tmp_path)
    raw = json.loads((tmp_path / "decision_latest.json").read_text(encoding="utf-8"))
    strings: list = []
    _collect_strings(raw, strings)
    for s in strings:
        for sub in FORBIDDEN_PROSE_SUBSTRINGS:
            assert sub not in s, f"Persisted value must not contain prose {sub!r}: {s[:80]!r}"


def test_offline_proof_primary_reason_codes_strict_regex(tmp_path: Path) -> None:
    """R22.8: primary_reason_codes must match ^[A-Z0-9_]+$."""
    _run_offline_eval(FIXTURE_PATH, tmp_path)
    raw = json.loads((tmp_path / "decision_latest.json").read_text(encoding="utf-8"))
    for sym in raw.get("symbols") or []:
        if not isinstance(sym, dict):
            continue
        codes = sym.get("primary_reason_codes") or []
        for c in codes:
            assert isinstance(c, str), f"primary_reason_codes element must be str: {c}"
            assert STRICT_CODE_RE.match(c), f"primary_reason_codes must match ^[A-Z0-9_]+$: {c!r}"


def test_offline_proof_golden_determinism(tmp_path: Path) -> None:
    """R22.8: Run offline eval twice; score/band/verdict must be identical (golden determinism)."""
    art1 = _run_offline_eval(FIXTURE_PATH, tmp_path)
    out2 = tmp_path / "run2"
    out2.mkdir(parents=True, exist_ok=True)
    art2 = _run_offline_eval(FIXTURE_PATH, out2)

    symbols1 = {s.symbol: s for s in (art1.symbols or []) if getattr(s, "symbol", "")}
    symbols2 = {s.symbol: s for s in (art2.symbols or []) if getattr(s, "symbol", "")}
    assert set(symbols1) == set(symbols2), "Same fixture must produce same symbol set"
    for sym in symbols1:
        s1 = symbols1[sym]
        s2 = symbols2[sym]
        assert s1.score == s2.score, f"{sym}: score must match ({s1.score} vs {s2.score})"
        assert s1.band == s2.band, f"{sym}: band must match ({s1.band} vs {s2.band})"
        assert s1.verdict == s2.verdict, f"{sym}: verdict must match ({s1.verdict} vs {s2.verdict})"
        assert (s1.primary_reason_codes or []) == (s2.primary_reason_codes or []), (
            f"{sym}: primary_reason_codes must match"
        )


def test_offline_proof_writes_eval_snapshot(tmp_path: Path) -> None:
    """R22.8: Offline run must write eval_snapshot.json."""
    _run_offline_eval(FIXTURE_PATH, tmp_path)
    snapshot_file = tmp_path / "eval_snapshot.json"
    assert snapshot_file.exists(), "eval_snapshot.json must be written"
    snap = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert "snapshot_id" in snap or "created_at" in snap
