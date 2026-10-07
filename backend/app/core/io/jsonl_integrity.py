# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 17.0: JSONL integrity scan and repair — detect invalid lines, repair with backup."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_store_paths() -> Dict[str, Path]:
    """Phase 17.0: Paths for key JSONL stores (notifications, diagnostics_history, positions_events)."""
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    try:
        from app.core.positions.store import _get_positions_dir
        pos_dir = _get_positions_dir()
    except Exception:
        pos_dir = out / "positions"
    return {
        "notifications": out / "notifications.jsonl",
        "diagnostics_history": out / "diagnostics_history.jsonl",
        "positions_events": pos_dir / "positions_events.jsonl",
    }


def scan_jsonl(path: Path) -> Dict[str, Any]:
    """
    Scan JSONL file for integrity.
    Returns {total_lines, invalid_lines, invalid_line_numbers[], last_valid_line, last_valid_offset}.
    """
    path = Path(path)
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "total_lines": 0,
            "invalid_lines": 0,
            "invalid_line_numbers": [],
            "last_valid_line": 0,
            "last_valid_offset": 0,
        }
    total_lines = 0
    invalid_lines = 0
    invalid_line_numbers: List[int] = []
    last_valid_line = 0
    last_valid_offset = 0
    offset = 0
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            total_lines += 1
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
                last_valid_line = line_num
                last_valid_offset = offset
            except (json.JSONDecodeError, TypeError):
                invalid_lines += 1
                invalid_line_numbers.append(line_num)
            offset += len(line.encode("utf-8"))
    return {
        "path": str(path),
        "exists": True,
        "total_lines": total_lines,
        "invalid_lines": invalid_lines,
        "invalid_line_numbers": invalid_line_numbers[:100],  # cap for response
        "last_valid_line": last_valid_line,
        "last_valid_offset": last_valid_offset,
    }


def repair_jsonl(path: Path) -> Dict[str, Any]:
    """
    Repair JSONL: keep only valid lines, write to path. Saves backup to path.<timestamp>.bak.
    Returns {valid_count, removed_count, backup_path}.
    """
    path = Path(path)
    if not path.exists():
        return {"valid_count": 0, "removed_count": 0, "backup_path": None}
    valid: List[str] = []
    removed = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
                valid.append(line.rstrip("\n"))
            except (json.JSONDecodeError, TypeError):
                removed += 1
    backup_name = f"{path.name}.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.bak"
    backup_path = path.parent / backup_name
    with open(backup_path, "w", encoding="utf-8") as f:
        for ln in valid:
            f.write(ln + "\n")
    content = "\n".join(valid) + ("\n" if valid else "")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)
    return {
        "valid_count": len(valid),
        "removed_count": removed,
        "backup_path": str(backup_path),
    }
