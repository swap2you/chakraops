# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 17.0: Atomic writes for JSON state files — write to .tmp, fsync, rename."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def atomic_write_json(path: Path, obj: Dict[str, Any], indent: int | None = 0) -> None:
    """
    Write JSON to path atomically: write to path.tmp, fsync, rename to path.
    On rename failure, tmp is left for manual inspection.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent, default=str)
            f.flush()
            if hasattr(f, "fileno") and f.fileno() >= 0:
                try:
                    import os
                    os.fsync(f.fileno())
                except OSError:
                    pass
        tmp_path.replace(path)
    except Exception as e:
        logger.warning("[ATOMIC] Failed to write %s: %s", path, e)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
