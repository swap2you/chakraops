# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 threshold registry — inherited provenance; runtime still strategy_profiles.yaml."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.core.decision_engine.threshold_registry import (
    ThresholdRegistryError,
    get_threshold_provenance,
    list_threshold_keys,
    load_threshold_registry,
)


def test_load_default_registry_all_inherited() -> None:
    data = load_threshold_registry()
    assert data["runtime_source"] == "strategy_profiles.yaml"
    for profile in ("conservative", "balanced", "aggressive"):
        keys = data["profiles"][profile]
        assert "csp_delta_range" in keys
        assert keys["csp_delta_range"]["source"] == "inherited"
        assert keys["csp_delta_range"]["evidence_path"] is None
        for meta in keys.values():
            assert meta["source"] == "inherited"


def test_get_threshold_provenance() -> None:
    p = get_threshold_provenance("balanced", "min_return_pct")
    assert p.source == "inherited"
    assert p.evidence_path is None
    assert p.runtime_source == "strategy_profiles.yaml"
    assert p.key == "min_return_pct"


def test_custom_inherits_balanced_provenance() -> None:
    p = get_threshold_provenance("custom", "cash_buffer_pct")
    assert p.source == "inherited"
    assert p.profile == "custom"


def test_list_threshold_keys_covers_liquidity_and_pm() -> None:
    keys = list_threshold_keys("aggressive")
    assert "liquidity.min_open_interest" in keys
    assert "profit_management.roll_at_dte" in keys
    assert keys["dte_range"]["source"] == "inherited"


def test_calibrated_without_evidence_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "threshold_registry.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            version: 1
            runtime_source: strategy_profiles.yaml
            profiles:
              balanced:
                min_return_pct: { source: calibrated, evidence_path: null }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ThresholdRegistryError, match="evidence_path"):
        load_threshold_registry(bad)


def test_unknown_key_raises() -> None:
    with pytest.raises(ThresholdRegistryError, match="unknown key"):
        get_threshold_provenance("balanced", "not_a_real_key")
