# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Exit plan: never silent blank; status NOT_AVAILABLE + reason when missing inputs."""

from __future__ import annotations

import pytest

from app.core.lifecycle.exit_planner import build_exit_plan


def test_exit_plan_with_atr_resistance_present():
    """When resistance_level (CSP) and ATR present, structure plan has T1/T2/stop."""
    el = {
        "support_level": 580.0,
        "resistance_level": 620.0,
        "computed": {"ATR14": 5.0},
        "regime": "UP",
    }
    st2 = {"selected_trade": {"exp": "2026-03-20", "strike": 600, "dte": 35}}
    ep = build_exit_plan("SPY", "CSP", 600.0, el, st2, None)
    assert ep["enabled"] is True
    sp = ep.get("structure_plan") or {}
    assert sp.get("T1") is not None
    assert sp.get("T2") is not None
    assert sp.get("stop_hint_price") is not None
    assert ep.get("missing_fields") == []


def test_exit_plan_missing_resistance_has_reason():
    """When resistance_level missing (CSP), missing_fields includes resistance_level."""
    el = {"support_level": 580.0, "computed": {"ATR14": 5.0}}
    st2 = {}
    ep = build_exit_plan("SPY", "CSP", 600.0, el, st2, None)
    assert ep["enabled"] is True
    assert "resistance_level" in (ep.get("missing_fields") or [])
    sp = ep.get("structure_plan") or {}
    assert sp.get("T1") is None
    assert sp.get("T2") is None


def test_exit_plan_missing_atr_stop_fallback():
    """When ATR missing but support present, stop can still be support level."""
    el = {"support_level": 580.0, "resistance_level": 620.0, "computed": {}}
    ep = build_exit_plan("SPY", "CSP", 600.0, el, {}, None)
    sp = ep.get("structure_plan") or {}
    assert sp.get("stop_hint_price") is not None
    assert sp.get("T1") is not None
