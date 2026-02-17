# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests: canonical store path, band_reason from score only (no verdict drift)."""

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestCanonicalStorePath:
    """Canonical path must be <REPO_ROOT>/out/decision_latest.json, not app/out."""

    def test_canonical_store_path_is_repo_out(self):
        """Store path ends with /out/decision_latest.json and is under repo root, not app/."""
        from app.core.eval.evaluation_store_v2 import get_decision_store_path

        path = get_decision_store_path()
        posix = path.as_posix()
        assert posix.endswith("/out/decision_latest.json"), (
            f"Expected path to end with /out/decision_latest.json, got {posix}"
        )
        assert "/app/out/" not in posix, (
            f"Path must not be under app/out (use repo root out/). Got {posix}"
        )
        # Should be under repo root (parent of chakraops)
        repo_root = _REPO.parent
        try:
            path.relative_to(repo_root)
        except ValueError:
            pytest.fail(f"Path {path} should be under repo root {repo_root}")


class TestBandReasonMatchesBand:
    """band_reason must be computed from same logic as band; never mention verdict."""

    def test_band_reason_matches_band_for_boundary_scores(self):
        """For each boundary score, band letter appears in reason and thresholds match."""
        from app.core.eval.decision_artifact_v2 import assign_band, assign_band_reason

        # Config: TIER_A=80, TIER_B=60, TIER_C=40
        cases = [
            (None, "D"),
            (0, "D"),
            (35, "D"),
            (39, "D"),
            (40, "C"),
            (49, "C"),
            (50, "C"),
            (59, "C"),
            (60, "B"),
            (79, "B"),
            (80, "A"),
            (89, "A"),
            (90, "A"),
        ]
        for score, expected_band in cases:
            band = assign_band(score)
            reason = assign_band_reason(score)
            assert band == expected_band, f"score={score}: expected band {expected_band}, got {band}"
            assert band in reason, f"score={score}: band {band} must appear in reason: {reason}"
            assert "verdict" not in reason.lower() and "HOLD" not in reason and "ELIGIBLE" not in reason, (
                f"band_reason must not mention verdict: {reason}"
            )

    def test_artifact_rows_have_consistent_band_reason(self, tmp_path):
        """Run evaluation on SPY,AAPL; each symbol row has band_reason matching band, no verdict."""
        from app.core.eval.decision_artifact_v2 import assign_band, assign_band_reason
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        try:
            artifact = evaluate_universe(["SPY", "AAPL"], mode="LIVE", output_dir=str(tmp_path))
        except Exception as e:
            pytest.skip(f"Evaluation requires ORATS: {e}")
        for s in artifact.symbols:
            band = s.band
            reason = s.band_reason or ""
            assert band in reason, f"Symbol {s.symbol}: band {band} must appear in band_reason: {reason}"
            assert "verdict" not in reason.lower(), f"band_reason must not mention verdict: {reason}"
            assert "HOLD" not in reason and "ELIGIBLE" not in reason
            # Consistency: assign_band(score) should match s.band
            assert assign_band(s.score) == band
            assert assign_band_reason(s.score) == reason


class TestSanityStoreInvariants:
    """Lightweight tests: store file invariants (no API)."""

    def test_store_file_has_required_structure(self, tmp_path):
        """After evaluation, store file has artifact_version, metadata, symbols."""
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        try:
            evaluate_universe(["SPY"], mode="LIVE", output_dir=str(tmp_path))
        except Exception as e:
            pytest.skip(f"Requires ORATS: {e}")
        store_path = tmp_path / "decision_latest.json"
        assert store_path.exists()
        with open(store_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("metadata") or data
        assert meta.get("artifact_version") == "v2"
        assert "pipeline_timestamp" in meta
        symbols = data.get("symbols", [])
        assert len(symbols) >= 1
        for s in symbols:
            assert s.get("band") is not None
            assert s.get("verdict") is not None
