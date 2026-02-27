# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
R22.8/R25.1: Offline proof harness — verify decision artifact hygiene and determinism without live market/ORATS.

Runs the same evaluation pipeline (evaluate_universe) with fixture-driven staged results,
writes artifacts via the same store (decision_latest.json, eval_snapshot.json) into a temp
out/ directory by default (no pollution of repo out/), then runs hygiene checks and prints
a per-symbol summary.

Usage (from repo root):
  python chakraops/scripts/offline_eval_proof.py --fixture chakraops/tests/fixtures/r25_1_offline_fixture.json

Or from chakraops dir:
  python scripts/offline_eval_proof.py --fixture tests/fixtures/r25_1_offline_fixture.json

R25.1: Default --output-dir is a temp directory. Use --output-dir out to write to repo out/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, List

# Ensure chakraops is on path when run from repo root
_SCRIPT_DIR = Path(__file__).resolve().parent
_CHAKRAOPS_ROOT = _SCRIPT_DIR.parent
if str(_CHAKRAOPS_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHAKRAOPS_ROOT))


# Hygiene: same rules as test_decision_artifact_hygiene_r227 (no prose, no FAIL_/WARN_)
FORBIDDEN_PATTERNS = [
    re.compile(r"\bFAIL_[A-Z0-9_]+\b"),
    re.compile(r"\bWARN_[A-Z0-9_]+\b"),
]
FORBIDDEN_PROSE_SUBSTRINGS = [
    "caps score",
    "Not evaluated",
    "Exit plan not computed",
    "High data completeness",
    "Regime NEUTRAL",
    "Regime RISK_ON",
]


def _collect_strings(obj: Any, out: List[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, out)
    elif isinstance(obj, str):
        out.append(obj)


def run_hygiene_check(data: dict) -> List[str]:
    """Return list of violation messages. Empty if PASS."""
    violations: List[str] = []
    strings: List[str] = []
    _collect_strings(data, strings)
    for s in strings:
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(s):
                violations.append(f"Forbidden pattern {pat.pattern!r}: {s[:80]!r}...")
        for sub in FORBIDDEN_PROSE_SUBSTRINGS:
            if sub in s:
                violations.append(f"Prose substring {sub!r}: {s[:80]!r}...")
        if " " in s:
            violations.append(f"String contains space (prose): {s[:80]!r}...")
    # applied_caps must have reason_code, not reason (walk symbols and diagnostics)
    symbols_list = data.get("symbols") or []
    for idx, val in enumerate(symbols_list):
        if not isinstance(val, dict):
            continue
        sb = val.get("score_breakdown") or {}
        for i, cap in enumerate(sb.get("applied_caps") or []):
            if isinstance(cap, dict) and "reason" in cap:
                violations.append(f"symbols[{idx}].score_breakdown.applied_caps[{i}]: has 'reason', use reason_code only")
            if isinstance(cap, dict) and not cap.get("reason_code"):
                violations.append(f"symbols[{idx}].score_breakdown.applied_caps[{i}]: missing reason_code")
    diag = data.get("diagnostics_by_symbol") or {}
    for sym, d in diag.items():
        if not isinstance(d, dict):
            continue
        sb = d.get("score_breakdown") or {}
        for i, cap in enumerate(sb.get("applied_caps") or []):
            if isinstance(cap, dict) and "reason" in cap:
                violations.append(f"diagnostics_by_symbol.{sym}.applied_caps[{i}]: has 'reason'")
            if isinstance(cap, dict) and not cap.get("reason_code"):
                violations.append(f"diagnostics_by_symbol.{sym}.applied_caps[{i}]: missing reason_code")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="R25.1 Offline proof: run eval from fixture, check hygiene.")
    parser.add_argument(
        "--fixture",
        type=str,
        default="tests/fixtures/r25_1_offline_fixture.json",
        help="Path to fixture JSON (repo-relative or absolute)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for decision_latest.json (default: temp dir; use 'out' for repo out/)",
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.is_absolute():
        repo_root = _CHAKRAOPS_ROOT.parent
        if (repo_root / args.fixture).exists():
            fixture_path = repo_root / args.fixture
        elif (_CHAKRAOPS_ROOT / args.fixture).exists():
            fixture_path = _CHAKRAOPS_ROOT / args.fixture
        else:
            fixture_path = Path.cwd() / args.fixture
    if not fixture_path.exists():
        print(f"FAIL: Fixture not found: {fixture_path}")
        return 1

    # R25.1: Default to temp dir so repo out/ is not polluted
    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
        if not out_dir.is_absolute() and not args.output_dir.startswith(("out", "/", "\\")):
            out_dir = Path.cwd() / args.output_dir
        out_dir = out_dir.resolve()
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="chakraops_offline_proof_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir}")

    from app.core.eval.offline_fixture_provider import build_universe_result_from_fixture, load_fixture
    from app.core.eval.evaluation_service_v2 import evaluate_universe
    from app.core.eval.evaluation_store_v2 import (
        set_output_dir,
        reset_output_dir,
    )
    from unittest.mock import patch

    symbols = load_fixture(fixture_path).get("symbols") or []
    if not symbols:
        print("FAIL: Fixture has no symbols")
        return 1

    set_output_dir(out_dir)
    try:
        mock_result = build_universe_result_from_fixture(fixture_path)
        with patch("app.core.eval.universe_evaluator.run_universe_evaluation_staged", return_value=mock_result):
            artifact = evaluate_universe(symbols, mode="LIVE")
    finally:
        reset_output_dir()

    decision_file = out_dir / "decision_latest.json"
    if not decision_file.exists():
        print("FAIL: decision_latest.json was not written")
        return 1

    with open(decision_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    violations = run_hygiene_check(raw)
    if violations:
        print("Artifact hygiene check: FAIL")
        for v in violations[:20]:
            print(f"  - {v}")
        if len(violations) > 20:
            print(f"  ... and {len(violations) - 20} more")
        return 1
    print("Artifact hygiene check: PASS")

    snapshot_path = out_dir / "eval_snapshot.json"
    if snapshot_path.exists():
        print("Snapshot written: PASS")
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snap = json.load(f)
            print(f"  snapshot_id={snap.get('snapshot_id')} created_at={snap.get('created_at')}")
        except Exception:
            pass
    else:
        print("Snapshot written: FAIL (eval_snapshot.json not found)")
        return 1

    print("\nPer-symbol summary:")
    for s in getattr(artifact, "symbols", []) or []:
        sym = getattr(s, "symbol", "") or ""
        score = getattr(s, "score", None)
        band = getattr(s, "band", "") or ""
        verdict = getattr(s, "verdict", "") or ""
        codes = getattr(s, "primary_reason_codes", []) or []
        print(f"  {sym}: score={score} band={band} verdict={verdict} primary_reason_codes={codes}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
