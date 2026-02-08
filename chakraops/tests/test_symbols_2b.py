# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2B: Symbol intelligence tests — explain, candidates, targets."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.market.company_data import get_company_metadata
from app.core.symbols.explain import get_symbol_explain
from app.core.symbols.candidates import get_symbol_candidates
from app.core.symbols.targets import get_targets, put_targets


# ---------------------------------------------------------------------------
# Company metadata
# ---------------------------------------------------------------------------


def test_company_metadata_known_symbol() -> None:
    meta = get_company_metadata("NVDA")
    assert meta is not None
    assert meta["symbol"] == "NVDA"
    assert meta["name"] == "NVIDIA Corp"
    assert meta["sector"] == "Technology"


def test_company_metadata_unknown_symbol() -> None:
    meta = get_company_metadata("UNKNOWNXYZ")
    assert meta is None


def test_company_metadata_empty() -> None:
    meta = get_company_metadata("")
    assert meta is None


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------


def test_explain_returns_structure() -> None:
    r = get_symbol_explain("NVDA")
    assert "symbol" in r
    assert r["symbol"] == "NVDA"
    assert "company" in r
    assert "gates" in r
    assert "primary_strategy" in r
    assert "strategy_why_bullets" in r
    assert "data_coverage" in r


def test_explain_gate_trace_presence() -> None:
    r = get_symbol_explain("AAPL")
    assert isinstance(r["gates"], list)
    for g in r["gates"]:
        assert "name" in g
        assert "status" in g
        assert g["status"] in ("PASS", "FAIL", "WAIVED", "UNKNOWN") or "reason" in g


def test_explain_strategy_exclusive() -> None:
    r = get_symbol_explain("SPY")
    strat = r.get("primary_strategy")
    assert strat is None or strat in ("CSP", "CC", "STOCK")


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


def test_candidates_returns_structure() -> None:
    r = get_symbol_candidates("NVDA", "CSP")
    assert "symbol" in r
    assert "strategy" in r
    assert "candidates" in r
    assert isinstance(r["candidates"], list)
    assert len(r["candidates"]) <= 3


def test_candidates_strategy_filter() -> None:
    r = get_symbol_candidates("AAPL", "CSP")
    assert r["strategy"] == "CSP"
    for c in r["candidates"]:
        assert "rank" in c
        assert "strike" in c or c.get("strike") is None
        assert "expiration" in c or c.get("expiration") is None
        assert "label" in c


def test_candidates_output_shape() -> None:
    r = get_symbol_candidates("MSFT", "CSP")
    for c in r.get("candidates", []):
        assert "rank" in c
        assert "label" in c
        assert "premium_per_contract" in c
        assert "collateral_per_contract" in c


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def test_targets_get_put_roundtrip(tmp_path: Path) -> None:
    import app.core.symbols.targets as targets_mod
    with patch.object(targets_mod, "_get_targets_dir", return_value=tmp_path):
        put_targets("TESTTGT", {
            "entry_low": 100.0,
            "entry_high": 105.0,
            "stop": 95.0,
            "target1": 110.0,
            "target2": 115.0,
            "notes": "Test notes",
        })
        t = get_targets("TESTTGT")
        assert t["symbol"] == "TESTTGT"
        assert t["entry_low"] == 100.0
        assert t["entry_high"] == 105.0
        assert t["stop"] == 95.0
        assert t["target1"] == 110.0
        assert t["target2"] == 115.0
        assert t["notes"] == "Test notes"

    with patch.object(targets_mod, "_get_targets_dir", return_value=tmp_path):
        t2 = get_targets("TESTTGT")
        assert t2["entry_low"] == 100.0


def test_targets_get_empty_returns_defaults() -> None:
    t = get_targets("NONEXISTENTSYMBOL123")
    assert t["symbol"] == "NONEXISTENTSYMBOL123"
    assert t["entry_low"] is None
    assert t["entry_high"] is None
    assert t["stop"] is None
    assert t["target1"] is None
    assert t["target2"] is None
    assert t["notes"] == ""


def test_targets_put_validates_symbol() -> None:
    with pytest.raises(ValueError):
        put_targets("", {})
