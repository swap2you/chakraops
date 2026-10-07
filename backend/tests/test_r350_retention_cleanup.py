# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 retention cleanup job."""

from __future__ import annotations

from unittest.mock import patch


def test_retention_job():
    from app.core.operations.jobs.retention_cleanup_job import _run

    with patch("app.core.operations.backup_service.cleanup_expired_backups") as mock_clean:
        mock_clean.return_value = {"removed": ["old"], "retained": 10}
        result = _run()
    assert "old" in result["output_refs"]
