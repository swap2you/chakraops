# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 weekly refresh job wrapper."""

from __future__ import annotations

from unittest.mock import patch


def test_weekly_refresh_job_delegates():
    from app.core.operations.jobs.weekly_refresh_job import _run

    with patch("app.core.universe.weekly_refresh.apply_weekly_universe_refresh") as mock_apply:
        mock_apply.return_value = {"status": "applied"}
        result = _run()
    assert result["metadata"]["status"] == "applied"
