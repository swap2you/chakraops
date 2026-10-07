# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5 health gate: dry-run unit test with mocked data. No network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Import checklist from script (no network)
SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
HEALTH_GATE_SCRIPT = SCRIPT_DIR / "health_gate_phase5.py"


def _load_health_gate_module():
    spec = importlib.util.spec_from_file_location("health_gate_phase5", HEALTH_GATE_SCRIPT)
    if spec is None or spec.loader is None:
        pytest.skip("health_gate_phase5.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["health_gate_phase5"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_health_gate_checklist_structure_and_no_crash():
    """Dry run: _eval_checklist with mocked data returns (passes, warns, fails) and does not crash."""
    mod = _load_health_gate_module()
    _eval_checklist = getattr(mod, "_eval_checklist", None)
    assert _eval_checklist is not None, "script must expose _eval_checklist"

    # Mock: enough candles, valid eligibility trace, minimal stage2
    candles = []
    for i in range(350):
        d = (i % 365) + 1
        candles.append({
            "ts": f"2024-{(d // 31) + 1:02d}-{(d % 28) + 1:02d}",
            "tradeDate": f"2024-{(d // 31) + 1:02d}-{(d % 28) + 1:02d}",
            "open": 100.0 + i * 0.01,
            "high": 101.0 + i * 0.01,
            "low": 99.0 + i * 0.01,
            "close": 100.0 + i * 0.01,
        })
    candles.sort(key=lambda c: (c["ts"], c.get("close", 0)))

    eligibility_trace = {
        "mode_decision": "NONE",
        "primary_reason_code": "FAIL_RSI_CSP",
        "rejection_reason_codes": ["FAIL_RSI_CSP"],
        "regime": "UP",
        "rsi14": 65.0,
        "ema20": 100.0,
        "ema50": 99.0,
        "atr_pct": 0.02,
        "method": "swing_cluster",
        "tolerance_used": 0.5,
        "support_level": 98.0,
        "resistance_level": 102.0,
        "rule_checks": [
            {"name": "RSI_IN_RANGE_CSP", "passed": False, "actual": 65.0, "threshold": (40, 60), "reason_code": "FAIL_RSI_CSP"},
            {"name": "NEAR_SUPPORT", "passed": True, "actual": 0.02, "threshold": 0.02, "reason_code": "FAIL_NOT_NEAR_SUPPORT"},
        ],
    }
    stage2_trace = {}  # NONE -> no stage2
    spot_used = 100.0
    artifacts_written = {"eligibility_trace": True, "stage2_trace": False, "candles": True}

    passes, warns, fails = _eval_checklist(
        "SPY", candles, eligibility_trace, stage2_trace, spot_used, artifacts_written
    )

    assert isinstance(passes, list)
    assert isinstance(warns, list)
    assert isinstance(fails, list)
    # Should have some passes (data rows, method, artifacts, etc.)
    assert len(passes) >= 3
    # Required checklist categories present in output (as lines)
    all_lines = [s.strip() for s in passes + warns + fails]
    assert any("DATA" in s for s in all_lines)
    assert any("INDICATORS" in s for s in all_lines)
    assert any("S/R" in s or "S/R" in s for s in all_lines)
    assert any("ELIGIBILITY" in s for s in all_lines)
    assert any("MODE_INTEGRITY" in s or "ARTIFACTS" in s for s in all_lines)


def test_health_gate_checklist_empty_candles():
    """Checklist with no candles: fails DATA and does not crash."""
    mod = _load_health_gate_module()
    _eval_checklist = getattr(mod, "_eval_checklist", None)
    assert _eval_checklist is not None

    passes, warns, fails = _eval_checklist(
        "X", [], None, None, None, {}
    )
    assert isinstance(passes, list)
    assert isinstance(fails, list)
    assert any("DATA" in f and "rows" in f for f in fails)
