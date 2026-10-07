# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.9: Cache pruner."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.data.cache_pruner import prune_cache


def test_prune_by_age(tmp_path: Path):
    """prune_cache removes files older than max_age_days."""
    (tmp_path / "a.json").write_text('{"x":1}')
    (tmp_path / "b.json").write_text('{"x":2}')
    old_time = time.time() - (8 * 86400)
    import os
    os.utime(tmp_path / "a.json", (old_time, old_time))

    result = prune_cache(tmp_path, max_age_days=7, max_files=10000)
    assert result["deleted"] >= 1
    assert result["remaining"] <= 1
    assert not (tmp_path / "a.json").exists()


def test_prune_by_max_files(tmp_path: Path):
    """prune_cache deletes oldest when remaining > max_files."""
    for i in range(15):
        (tmp_path / f"f{i}.json").write_text(f'{{"i":{i}}}')
        (tmp_path / f"f{i}.json").touch()
        time.sleep(0.01)

    result = prune_cache(tmp_path, max_age_days=30, max_files=5)
    assert result["deleted"] >= 10
    assert result["remaining"] <= 5
