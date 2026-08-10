# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 grounded advisor + education goal planner API (no broker writes)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.advisor.grounding_r58 import build_goal_plan, build_grounded_answer

router = APIRouter(prefix="/api/ui/advisor", tags=["advisor-r58"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.post("/ask")
async def advisor_ask(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return build_grounded_answer(
        question=str(body.get("question") or ""),
        citations=list(body.get("citations") or []),
        answer=str(body.get("answer") or ""),
        confidence=str(body.get("confidence") or "low"),
    )


@router.post("/goal-plan")
async def advisor_goal_plan(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return build_goal_plan(
        goal=str(body.get("goal") or ""),
        horizon_months=int(body.get("horizon_months") or 12),
        constraints=body.get("constraints") if isinstance(body.get("constraints"), dict) else {},
    )


@router.get("/status")
def advisor_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return {
        "status": "OK",
        "mode": "grounded_advisory",
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
    }
