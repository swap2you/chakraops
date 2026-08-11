# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 grounded advisor + education goal planner API (no broker writes)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.advisor.deepen_r68 import deepen_ask, education_catalog
from app.core.advisor.grounding_r58 import build_goal_plan

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
    """Grounded ask — server synthesizes answers; client prose is not trusted (R70-DEF-060)."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    # Ignore body["answer"] for default ask; deepen modes generate server-side.
    return deepen_ask(
        question=str(body.get("question") or ""),
        citations=list(body.get("citations") or []),
        answer="",  # never trust client answer on public ask
        confidence=str(body.get("confidence") or "low"),
        mode=str(body.get("mode") or "ask"),
        teach_topic=body.get("teach_topic"),
        compare_left=body.get("compare_left"),
        compare_right=body.get("compare_right"),
        no_trade_reasons=list(body.get("no_trade_reasons") or [])
        if isinstance(body.get("no_trade_reasons"), list)
        else None,
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


@router.get("/education")
def advisor_education(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return education_catalog()


@router.get("/status")
def advisor_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return {
        "status": "OK",
        "mode": "grounded_advisory",
        "answer_source": "server_synthesized",
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
    }
