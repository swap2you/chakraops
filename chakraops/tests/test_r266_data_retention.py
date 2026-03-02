# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.6: Data retention — ensure data/reports path is configurable (no hardcoded OS paths)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_monthly_close_store_base_path_override() -> None:
    """monthly_close_store _reports_base_path() uses override when set; no hardcoded OS path in tests."""
    from app.core.ops.monthly_close_store_r265 import (
        _reports_base_path,
        set_reports_base_path,
        reset_reports_base_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        override = Path(tmp) / "reports"
        set_reports_base_path(override)
        try:
            assert _reports_base_path().resolve() == override.resolve()
        finally:
            reset_reports_base_path()
    # After reset, path is repo-relative (parents[3] / "data" / "reports"), not a fixed OS path
    base = _reports_base_path()
    assert "data" in base.parts
    assert "reports" in base.parts
