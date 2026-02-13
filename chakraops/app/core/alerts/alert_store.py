# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.0: Persist alert payload to disk. No Slack send."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


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
