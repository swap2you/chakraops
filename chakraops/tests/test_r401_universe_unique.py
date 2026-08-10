# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: universe.csv unique symbol count."""

from __future__ import annotations

from pathlib import Path


def test_universe_csv_unique_sorted() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "universe.csv"
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Allow leading comment lines
    while lines and lines[0].startswith("#"):
        lines = lines[1:]
    assert lines[0].lower().startswith("symbol")
    syms = [ln.strip().upper() for ln in lines[1:] if ln.strip() and not ln.startswith("#")]
    assert len(syms) == len(set(syms)), f"duplicates: {[s for s in syms if syms.count(s) > 1]}"
    assert syms == sorted(syms)
    assert len(syms) == 166
