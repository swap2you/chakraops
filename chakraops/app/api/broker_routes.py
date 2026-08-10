# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R37 broker status API — read-only NO-GO surface; no credentials."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header

from app.core.broker.read_only_policy import robinhood_integration_status

router = APIRouter(prefix="/api/ui/broker", tags=["broker"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    """Reuse UI key gate when UI_API_KEY is set (local dev allows when unset)."""
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    from fastapi import HTTPException

    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/status")
def broker_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    """Return Robinhood integration NO-GO status (no credentials, no sync)."""
    _require_ui_key(x_ui_key)
    return robinhood_integration_status()
