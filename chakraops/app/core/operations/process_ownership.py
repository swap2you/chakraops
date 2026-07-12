# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Track ChakraOps-owned process PIDs for safe Windows shutdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.chakraops_ports import BACKEND_PORT, FRONTEND_PORT

REPO_ROOT_EXPECTED = r"C:\Development\Workspace\ChakraOps-dev\chakraops"
STALE_CHECKOUT_MARKER = r"C:\Development\Workspace\ChakraOps"


def ownership_path() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "process_ownership.json"


def write_record(
    *,
    backend_pid: int,
    frontend_pid: int,
    repo_root: str,
    backend_cmd: str,
    frontend_cmd: str,
    backend_port: int = BACKEND_PORT,
    frontend_port: int = FRONTEND_PORT,
) -> Dict[str, Any]:
    record = {
        "repo_root": repo_root,
        "backend_pid": backend_pid,
        "frontend_pid": frontend_pid,
        "backend_cmd": backend_cmd,
        "frontend_cmd": frontend_cmd,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ownership_path().write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def read_record() -> Optional[Dict[str, Any]]:
    path = ownership_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def clear_record() -> None:
    path = ownership_path()
    if path.exists():
        path.unlink()


def validate_repo_root(repo_root: str) -> None:
    normalized = str(repo_root).replace("/", "\\").rstrip("\\")
    if STALE_CHECKOUT_MARKER.lower() == normalized.lower():
        raise ValueError("stale checkout path detected; use ChakraOps-dev")
    expected = REPO_ROOT_EXPECTED.replace("/", "\\").rstrip("\\")
    if normalized.lower() != expected.lower():
        raise ValueError(f"unexpected repo root: {repo_root}")
