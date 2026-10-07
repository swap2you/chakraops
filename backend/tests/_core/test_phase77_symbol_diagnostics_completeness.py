# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.7: Guardrail tests — symbol diagnostics completeness, store consistency."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestPhase77SymbolDiagnosticsCompleteness:
    """Tests that would have caught the 7.6.x regression."""

    def test_evaluate_universe_produces_diagnostics_for_symbol(self, tmp_path):
        """Run evaluate_universe, load store, assert diagnostics_details exists and has required structure."""
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        artifact = evaluate_universe(["SPY"], mode="LIVE", output_dir=str(tmp_path))
        assert artifact is not None

        store = get_evaluation_store_v2()
        row = store.get_symbol("SPY")
        assert row is not None
        summary, candidates, gates, earnings, diagnostics_details = row

        assert summary is not None
        assert summary.score is not None or summary.verdict == "NOT_EVALUATED"
        assert summary.band is not None and summary.band in ("A", "B", "C", "D")

        assert diagnostics_details is not None
        diag = diagnostics_details.to_dict() if hasattr(diagnostics_details, "to_dict") else diagnostics_details
        assert "technicals" in diag
        assert "rsi" in diag["technicals"] or "atr" in diag["technicals"]
        assert "exit_plan" in diag
        assert "t1" in diag["exit_plan"] or "stop" in diag["exit_plan"]
        assert "explanation" in diag
        assert "risk_flags" in diag
        assert "stock" in diag
        assert "symbol_eligibility" in diag
        assert "liquidity" in diag
        assert candidates is not None

    def test_api_symbol_diagnostics_has_required_keys(self, tmp_path):
        """Call /api/ui/symbol-diagnostics and assert response has known-good shape."""
        pytest.importorskip("fastapi")
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        evaluate_universe(["SPY"], mode="LIVE", output_dir=str(tmp_path))

        from fastapi.testclient import TestClient
        from app.api.server import app

        client = TestClient(app)
        resp = client.get("/api/ui/symbol-diagnostics?symbol=SPY")
        assert resp.status_code == 200
        data = resp.json()

        required = [
            "symbol", "verdict", "primary_reason", "composite_score", "confidence_band",
            "gates", "candidates", "exit_plan", "computed", "explanation",
            "symbol_eligibility", "liquidity", "provider_status",
        ]
        for k in required:
            assert k in data, f"Missing key: {k}"

        assert "technicals" in data.get("computed", {}) or "rsi" in str(data.get("computed"))
        ep = data.get("exit_plan") or {}
        assert "t1" in ep or "stop" in ep

    def test_universe_and_symbol_diagnostics_agree(self, tmp_path):
        """Universe row for SPY score/band equals symbol-diagnostics summary score/band."""
        pytest.importorskip("fastapi")
        from app.core.eval.evaluation_service_v2 import evaluate_universe

        evaluate_universe(["SPY"], mode="LIVE", output_dir=str(tmp_path))

        from fastapi.testclient import TestClient
        from app.api.server import app

        client = TestClient(app)
        uni = client.get("/api/ui/universe")
        assert uni.status_code == 200
        uni_data = uni.json()
        spy_row = next((s for s in uni_data.get("symbols", []) if s.get("symbol") == "SPY"), None)
        assert spy_row is not None

        diag = client.get("/api/ui/symbol-diagnostics?symbol=SPY")
        assert diag.status_code == 200
        diag_data = diag.json()

        assert spy_row.get("score") == diag_data.get("composite_score"), "Universe score must match symbol-diagnostics"
        assert spy_row.get("band") == diag_data.get("confidence_band"), "Universe band must match symbol-diagnostics"
