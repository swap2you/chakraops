# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R60 observability API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException

from app.core.ops.observability_r60 import connected_observability_status

router = APIRouter(prefix="/api/ui/observability", tags=["observability-r60"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/status")
def observability_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return connected_observability_status()
