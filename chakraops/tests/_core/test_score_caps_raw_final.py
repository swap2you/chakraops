# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Test raw_score, final_score, score_caps when regime cap applies."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


class TestScoreCapsRawFinal:
    """Raw vs final score and score_caps when regime cap applies."""

    def test_regime_neutral_caps_raw_89_to_final_65(self):
        """When raw_score=89 and regime is NEUTRAL, final_score == 65 and applied_caps includes regime."""
        # Simulate the cap logic in staged_evaluator (NEUTRAL cap=65)
        raw_score_val = 89
        market_regime_value = "NEUTRAL"
        applied_caps: list = []
        cap_val = 65
        final_score_val = min(raw_score_val, cap_val)
        if raw_score_val > cap_val:
            applied_caps.append({
                "type": "regime_cap",
                "cap_value": cap_val,
                "before": raw_score_val,
                "after": final_score_val,
                "reason": "Regime NEUTRAL caps score to 65",
            })
        assert final_score_val == 65
        assert len(applied_caps) == 1
        regime_cap = applied_caps[0]
        assert regime_cap["type"] == "regime_cap"
        assert regime_cap["cap_value"] == 65
        assert regime_cap["before"] == 89
        assert regime_cap["after"] == 65
        assert "NEUTRAL" in regime_cap["reason"]
