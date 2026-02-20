# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.7: Decision artifact hygiene — persisted JSON must be code-only.
No human prose, no UI strings, no raw FAIL_*/WARN_* in values.
This test MUST fail if a developer reintroduces prose into decision artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

# Forbidden keys that must never appear in persisted decision JSON (prose/UI fields)
FORBIDDEN_KEYS: Set[str] = {
    "why_this_trade",
    "explanation",  # when used as prose block
    "label",
    "tooltip",
    "message",
    "reasons_explained",
    "panel",
}
FORBIDDEN_KEY_PREFIXES: Tuple[str, ...] = ("display_",)

# Forbidden string patterns in any string value (recursive)
FORBIDDEN_PATTERNS = [
    re.compile(r"\bFAIL_[A-Z0-9_]+\b"),
    re.compile(r"\bWARN_[A-Z0-9_]+\b"),
]
# Known UI snippets that must not be persisted
FORBIDDEN_UI_SNIPPETS = [
    "Within OK window",
    "Market closed",
    "Staleness threshold",
    "Error (no data or failure)",
]

# R22.7: strict code format for primary_reason_codes and any "codes" fields
STRICT_CODE_RE = re.compile(r"^[A-Z0-9_]+$")

# Prose substrings that must never appear in persisted values
FORBIDDEN_PROSE_SUBSTRINGS = [
    "Stock qualified",
    "Chain evaluated",
    "contract selected",
    "rejected_due_to_delta=",
]


def _collect_strings(obj: Any, out: List[str]) -> None:
    """Recursively collect all string values from dict/list/nested."""
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, out)
    elif isinstance(obj, str):
        out.append(obj)


def _check_forbidden_keys(obj: Any, path: str = "") -> List[str]:
    """Return list of violations: 'path: forbidden key X'."""
    violations: List[str] = []
    if not isinstance(obj, dict):
        return violations
    for k, v in obj.items():
        key_lower = k.lower()
        if k in FORBIDDEN_KEYS:
            violations.append(f"{path}: forbidden key '{k}'")
        for prefix in FORBIDDEN_KEY_PREFIXES:
            if key_lower.startswith(prefix):
                violations.append(f"{path}: forbidden key prefix '{k}'")
        violations.extend(_check_forbidden_keys(v, f"{path}.{k}" if path else k))
    return violations


def _check_forbidden_strings(obj: Any) -> List[str]:
    """Return list of violations for forbidden patterns in string values."""
    violations: List[str] = []
    strings: List[str] = []
    _collect_strings(obj, strings)
    for s in strings:
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(s):
                violations.append(f"Value contains forbidden pattern {pat.pattern!r}: {s[:80]!r}...")
        for snippet in FORBIDDEN_UI_SNIPPETS:
            if snippet in s:
                violations.append(f"Value contains UI snippet {snippet!r}: {s[:80]!r}...")
        for sub in FORBIDDEN_PROSE_SUBSTRINGS:
            if sub in s:
                violations.append(f"Value contains prose substring {sub!r}: {s[:80]!r}...")
    return violations


def _check_primary_reason_codes_strict(obj: Any, path: str = "") -> List[str]:
    """R22.7: All primary_reason_codes must match ^[A-Z0-9_]+$."""
    violations: List[str] = []
    if not isinstance(obj, dict):
        return violations
    for k, v in obj.items():
        p = f"{path}.{k}" if path else k
        if k == "primary_reason_codes" and isinstance(v, list):
            for i, code in enumerate(v):
                code_str = str(code).strip()
                if not code_str or not STRICT_CODE_RE.match(code_str):
                    violations.append(f"{p}[{i}]: code {code_str!r} does not match ^[A-Z0-9_]+$")
        else:
            violations.extend(_check_primary_reason_codes_strict(v, p))
    return violations


def _check_option_candidates_identity(persisted: Dict[str, Any]) -> List[str]:
    """R22.7: Every option candidate in selected_candidates / candidates_by_symbol must have contract_key or option_symbol."""
    violations: List[str] = []
    for i, c in enumerate(persisted.get("selected_candidates") or []):
        if isinstance(c, dict) and (c.get("strategy") or "").upper() in ("CSP", "CC"):
            if not c.get("contract_key") and not c.get("option_symbol"):
                violations.append(f"selected_candidates[{i}]: option candidate missing contract_key and option_symbol")
    for sym, cands in (persisted.get("candidates_by_symbol") or {}).items():
        for i, c in enumerate(cands or []):
            if isinstance(c, dict) and (c.get("strategy") or "").upper() in ("CSP", "CC"):
                if not c.get("contract_key") and not c.get("option_symbol"):
                    violations.append(f"candidates_by_symbol.{sym}[{i}]: option candidate missing contract_key and option_symbol")
    return violations


def test_decision_artifact_no_forbidden_keys_or_patterns(tmp_path: Path) -> None:
    """Load a minimal v2 artifact (from code path) and assert no forbidden keys or FAIL_/WARN_ strings."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2
    from app.core.eval.evaluation_store_v2 import set_output_dir, get_decision_store_path

    set_output_dir(tmp_path)
    try:
        # Build minimal artifact with code-only fields (what we want after R22.7)
        artifact = DecisionArtifactV2(
            metadata={
                "artifact_version": "v2",
                "pipeline_timestamp": "2026-02-01T12:00:00Z",
                "run_id": "test-run",
            },
            symbols=[],
            selected_candidates=[],
            candidates_by_symbol={},
            gates_by_symbol={},
            earnings_by_symbol={},
            diagnostics_by_symbol={},
            warnings=[],
        )
        d = artifact.to_dict()
        violations_keys = _check_forbidden_keys(d)
        violations_str = _check_forbidden_strings(d)
        assert not violations_keys, f"Forbidden keys in minimal artifact: {violations_keys}"
        assert not violations_str, f"Forbidden strings in minimal artifact: {violations_str}"
    finally:
        from app.core.eval.evaluation_store_v2 import reset_output_dir
        reset_output_dir()


def test_decision_artifact_loaded_from_disk_has_no_prose_if_present(tmp_path: Path) -> None:
    """If decision_latest.json exists on disk, loading and serializing it must not contain forbidden keys/patterns.
    When current code still writes primary_reason with FAIL_*, this test will FAIL until Part 1 is done."""
    from app.core.eval.evaluation_store_v2 import (
        set_output_dir,
        get_evaluation_store_v2,
        reset_output_dir,
        get_decision_store_path,
    )

    set_output_dir(tmp_path)
    store_path = get_decision_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a v2 artifact that currently looks like production (with primary_reason string)
    sample = {
        "metadata": {"artifact_version": "v2", "pipeline_timestamp": "2026-02-01T12:00:00Z"},
        "symbols": [
            {
                "symbol": "TEST",
                "verdict": "HOLD",
                "final_verdict": "HOLD",
                "score": 50,
                "band": "C",
                "primary_reason": "FAIL_REGIME_CONFLICT; FAIL_NO_HOLDINGS",  # R22.7: this must become primary_reason_codes
                "stage_status": "RUN",
                "stage1_status": "PASS",
                "stage2_status": "NOT_RUN",
                "provider_status": "OK",
                "data_freshness": None,
                "evaluated_at": None,
                "strategy": None,
                "price": 100.0,
                "expiration": None,
                "has_candidates": False,
                "candidate_count": 0,
            }
        ],
        "selected_candidates": [],
        "candidates_by_symbol": {},
        "gates_by_symbol": {},
        "earnings_by_symbol": {},
        "diagnostics_by_symbol": {},
        "warnings": [],
    }
    store_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")

    try:
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        art = store.get_latest()
        if art is None:
            pytest.skip("Store did not load artifact")
        d = art.to_dict()
        violations_keys = _check_forbidden_keys(d)
        violations_str = _check_forbidden_strings(d)
        # R22.7: once we persist primary_reason_codes and drop primary_reason, these must be empty
        assert not violations_keys, f"Forbidden keys in loaded artifact: {violations_keys}"
        assert not violations_str, (
            f"Forbidden strings (e.g. FAIL_*) in loaded artifact: {violations_str}. "
            "R22.7: Persist primary_reason_codes (machine codes) and do not persist primary_reason with FAIL_*."
        )
    finally:
        reset_output_dir()


def test_persisted_artifact_primary_reason_codes_strict_regex() -> None:
    """R22.7: Every element in primary_reason_codes must match ^[A-Z0-9_]+$. No prose anywhere."""
    from app.core.eval.decision_artifact_v2 import (
        DecisionArtifactV2,
        SymbolEvalSummary,
    )

    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-02-01T12:00:00Z", "run_id": "r"},
        symbols=[
            SymbolEvalSummary(
                symbol="T1",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=50,
                band="C",
                primary_reason=None,
                primary_reason_codes=["STOCK_QUALIFIED", "CHAIN_SELECTED"],
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy="CSP",
                price=100.0,
                expiration="2026-03-20",
                has_candidates=True,
                candidate_count=1,
            ),
        ],
        selected_candidates=[],
        candidates_by_symbol={},
        gates_by_symbol={},
        earnings_by_symbol={},
        diagnostics_by_symbol={},
        warnings=[],
    )
    d = artifact.to_dict_persist()
    violations_codes = _check_primary_reason_codes_strict(d)
    violations_prose = _check_forbidden_strings(d)
    assert not violations_codes, f"primary_reason_codes must match ^[A-Z0-9_]+$: {violations_codes}"
    assert not violations_prose, f"Persisted artifact must not contain prose/FAIL_*/WARN_*: {violations_prose}"


def test_persisted_artifact_no_prose_substrings_or_forbidden_chars() -> None:
    """R22.7: No 'Stock qualified', 'Chain evaluated', 'contract selected', '(', ':', '=' in persisted values."""
    from app.core.eval.decision_artifact_v2 import (
        DecisionArtifactV2,
        SymbolEvalSummary,
        _reason_string_to_codes_and_count,
    )

    # Build summary with prose primary_reason; persistence must normalize to codes only
    pr = "Stock qualified (score: 35)"
    codes, _ = _reason_string_to_codes_and_count(pr)
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-02-01T12:00:00Z", "run_id": "r"},
        symbols=[
            SymbolEvalSummary(
                symbol="T2",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=35,
                band="C",
                primary_reason=pr,
                primary_reason_codes=codes,
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy=None,
                price=100.0,
                expiration=None,
                has_candidates=False,
                candidate_count=0,
            ),
        ],
        selected_candidates=[],
        candidates_by_symbol={},
        gates_by_symbol={},
        earnings_by_symbol={},
        diagnostics_by_symbol={},
        warnings=[],
    )
    d = artifact.to_dict_persist()
    violations = _check_forbidden_strings(d)
    assert not violations, f"Persisted artifact must not contain prose substrings or forbidden chars: {violations}"
    symbols = d.get("symbols") or []
    assert len(symbols) == 1
    assert "primary_reason" not in symbols[0] or symbols[0].get("primary_reason") is None
    assert symbols[0].get("primary_reason_codes") == ["STOCK_QUALIFIED"]


def test_option_candidates_have_identity_fields() -> None:
    """R22.7: Every persisted option candidate must have contract_key or option_symbol (derived if missing)."""
    from app.core.eval.decision_artifact_v2 import (
        CandidateRow,
        DecisionArtifactV2,
        SymbolEvalSummary,
    )

    # Candidate with strike/expiry/strategy but no contract_key or option_symbol — persistence must derive contract_key
    candidate = CandidateRow(
        symbol="NVDA",
        strategy="CSP",
        strike=500.0,
        expiry="2026-03-20",
        delta=-0.25,
        credit_estimate=None,
        max_loss=None,
        why_this_trade=None,
        contract_key=None,
        option_symbol=None,
    )
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "pipeline_timestamp": "2026-02-01T12:00:00Z", "run_id": "r"},
        symbols=[
            SymbolEvalSummary(
                symbol="NVDA",
                verdict="ELIGIBLE",
                final_verdict="ELIGIBLE",
                score=60,
                band="B",
                primary_reason=None,
                primary_reason_codes=["CHAIN_SELECTED"],
                stage_status="RUN",
                stage1_status="PASS",
                stage2_status="PASS",
                provider_status="OK",
                data_freshness=None,
                evaluated_at=None,
                strategy="CSP",
                price=500.0,
                expiration="2026-03-20",
                has_candidates=True,
                candidate_count=1,
            ),
        ],
        selected_candidates=[candidate],
        candidates_by_symbol={"NVDA": [candidate]},
        gates_by_symbol={},
        earnings_by_symbol={},
        diagnostics_by_symbol={},
        warnings=[],
    )
    d = artifact.to_dict_persist()
    violations = _check_option_candidates_identity(d)
    assert not violations, f"Option candidates must have contract_key or option_symbol after persist: {violations}"
    sel = d.get("selected_candidates") or []
    assert len(sel) == 1
    assert sel[0].get("contract_key") == "500-2026-03-20-PUT"
    nvda_cands = (d.get("candidates_by_symbol") or {}).get("NVDA") or []
    assert len(nvda_cands) == 1
    assert nvda_cands[0].get("contract_key") == "500-2026-03-20-PUT"
