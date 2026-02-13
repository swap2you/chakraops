# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.0: Persist alert payload to disk. No Slack send."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def save_alert_payload(
    payload: Dict[str, Any],
    base_dir: str = "artifacts/alerts",
) -> str:
    """
    Save payload as base_dir/<run_id>/<symbol>.json.
    Returns the absolute filepath written.
    """
    run_id = payload.get("run_id") or "unknown"
    symbol = (payload.get("symbol") or "UNKNOWN").strip().upper()
    path = Path(base_dir) / str(run_id) / f"{symbol}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return str(path.resolve())


def load_latest_alert_payload(
    symbol: str,
    base_dirs: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load the most recent alert payload for symbol from base_dirs/run_id/symbol.json.
    Tries each base_dir; within each, picks the run_id subdir with latest mtime, then loads symbol.json.
    Returns None if not found. Phase 7.3: used by send-trade-alert endpoint.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    if base_dirs is None:
        try:
            from app.core.settings import get_output_dir
            base = Path(get_output_dir())
        except Exception:
            base = Path("out")
        base_dirs = [str(base / "alerts"), "artifacts/alerts", "out/alerts"]
    for base_dir in base_dirs:
        root = Path(base_dir)
        if not root.exists():
            continue
        run_dirs = [d for d in root.iterdir() if d.is_dir()]
        if not run_dirs:
            continue
        latest_dir = max(run_dirs, key=lambda d: d.stat().st_mtime)
        path = latest_dir / f"{sym}.json"
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and (data.get("symbol") or "").strip().upper() == sym:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None
