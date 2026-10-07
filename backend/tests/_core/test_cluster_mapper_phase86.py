# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.6: Static Sector/Cluster Mapping V1."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.portfolio.cluster_mapper import get_symbol_tags, load_cluster_map


def test_get_symbol_tags_default_known_symbol():
    """Known symbol in DEFAULT_CLUSTER_MAP returns cluster and sector."""
    tags = get_symbol_tags("AAPL")
    assert tags["cluster"] == "MEGA_CAP_TECH"
    assert tags["sector"] == "TECH"
    assert tags["source"] == "DEFAULT"

    tags2 = get_symbol_tags("spy")  # case-insensitive
    assert tags2["cluster"] == "INDEX_ETF"
    assert tags2["sector"] == "ETF"
    assert tags2["source"] == "DEFAULT"

    tags3 = get_symbol_tags("XLE")
    assert tags3["cluster"] == "ENERGY_ETF"
    assert tags3["sector"] == "ENERGY"
    assert tags3["source"] == "DEFAULT"


def test_get_symbol_tags_unknown_symbol():
    """Unknown symbol returns UNKNOWN cluster and sector."""
    tags = get_symbol_tags("XYZ")
    assert tags["cluster"] == "UNKNOWN"
    assert tags["sector"] == "UNKNOWN"
    assert tags["source"] == "UNKNOWN"

    tags2 = get_symbol_tags("")
    assert tags2["cluster"] == "UNKNOWN"
    assert tags2["sector"] == "UNKNOWN"

    tags3 = get_symbol_tags(None)  # type: ignore
    assert tags3["cluster"] == "UNKNOWN"
    assert tags3["sector"] == "UNKNOWN"


def test_load_cluster_map_missing_file_returns_empty():
    """load_cluster_map returns {} when file does not exist."""
    result = load_cluster_map(Path("/nonexistent/path/cluster_map.json"))
    assert result == {}


def test_load_cluster_map_valid_file(tmp_path: Path):
    """load_cluster_map loads valid JSON and returns symbol->{cluster,sector}."""
    cfg = tmp_path / "cluster_map.json"
    cfg.write_text('{"CUSTOM": {"cluster": "MY_CLUSTER", "sector": "MY_SECTOR"}}')
    result = load_cluster_map(cfg)
    assert result == {"CUSTOM": {"cluster": "MY_CLUSTER", "sector": "MY_SECTOR"}}


def test_override_map_takes_precedence():
    """override_map takes precedence over DEFAULT_CLUSTER_MAP."""
    override = {"AAPL": {"cluster": "OVERRIDE_CLUSTER", "sector": "OVERRIDE_SECTOR"}}
    tags = get_symbol_tags("AAPL", override_map=override)
    assert tags["cluster"] == "OVERRIDE_CLUSTER"
    assert tags["sector"] == "OVERRIDE_SECTOR"
    assert tags["source"] == "OVERRIDE"

    # Symbol in override but not in DEFAULT: still uses override
    override2 = {"XYZ": {"cluster": "CUSTOM", "sector": "CUSTOM"}}
    tags2 = get_symbol_tags("XYZ", override_map=override2)
    assert tags2["cluster"] == "CUSTOM"
    assert tags2["sector"] == "CUSTOM"
    assert tags2["source"] == "OVERRIDE"

    # Symbol not in override, falls through to DEFAULT
    override3 = {"OTHER": {"cluster": "X", "sector": "Y"}}
    tags3 = get_symbol_tags("AAPL", override_map=override3)
    assert tags3["cluster"] == "MEGA_CAP_TECH"
    assert tags3["sector"] == "TECH"
    assert tags3["source"] == "DEFAULT"
