# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R54 advisory monitor status/run endpoints — read-only, no broker writes."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException

from app.core.monitor.advisory_worker_r54 import get_monitor_worker, monitor_status

router = APIRouter(prefix="/api/ui/monitor", tags=["monitor-r54"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/status")
def ui_monitor_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return monitor_status()


@router.post("/run-once")
def ui_monitor_run_once(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    signals = get_monitor_worker().run_once()
    return {
        "ok": True,
        "signal_count": len(signals),
        "signals": [s.to_dict() for s in signals],
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
    }
