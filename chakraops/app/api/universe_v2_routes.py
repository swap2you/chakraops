# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) read-only API — /api/ui/universe-v2/*.

Authoritative reads serve the precomputed published snapshot only (no provider calls,
no full recompute). ``POST /refresh`` performs an in-process manual build (no scheduler,
advisory-only). All routes are additive; legacy universe endpoints are untouched.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.universe_v2 import read_model
from app.core.universe_v2.model import ALL_STRATEGIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ui/universe-v2", tags=["universe-v2"])

_UI_API_KEY = (os.getenv("UI_API_KEY") or "").strip()


def _require_ui_key(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")) -> None:
    if not _UI_API_KEY:
        return
    if (x_ui_key or "").strip() != _UI_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/summary")
def universe_v2_summary(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    return read_model.summary()


@router.get("/research-pool")
def universe_v2_research_pool(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    return read_model.research_pool()


@router.get("/records")
def universe_v2_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    lifecycle: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    membership_status: Optional[str] = Query(None),
    x_ui_key: Optional[str] = Header(None, alias="x-ui-key"),
):
    _require_ui_key(x_ui_key)
    return read_model.records(
        page=page,
        page_size=page_size,
        lifecycle=lifecycle,
        strategy=strategy,
        membership_status=membership_status,
    )


@router.get("/records/{symbol}")
def universe_v2_record(symbol: str, x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    rec = read_model.record(symbol)
    if rec is None:
        raise HTTPException(status_code=404, detail="symbol not found in latest snapshot")
    return rec


@router.get("/membership/{strategy}")
def universe_v2_membership(strategy: str, x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    st = (strategy or "").strip().upper()
    if st not in ALL_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"unknown strategy; expected one of {list(ALL_STRATEGIES)}")
    return read_model.membership(st)


@router.get("/rejections")
def universe_v2_rejections(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    return read_model.rejections()


@router.get("/near-misses")
def universe_v2_near_misses(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    return read_model.near_misses()


@router.get("/transitions")
def universe_v2_transitions(
    limit: int = Query(50, ge=1, le=500),
    x_ui_key: Optional[str] = Header(None, alias="x-ui-key"),
):
    _require_ui_key(x_ui_key)
    return read_model.transitions(limit=limit)


@router.get("/freshness")
def universe_v2_freshness(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    _require_ui_key(x_ui_key)
    return read_model.freshness()


@router.post("/refresh")
def universe_v2_refresh(x_ui_key: Optional[str] = Header(None, alias="x-ui-key")):
    """Manual, in-process rebuild of the published snapshot from the latest evaluation
    artifact. No scheduler, no provider calls beyond what the existing artifact contains.
    Advisory-only."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.universe_v2.builder import build_universe_v2_snapshot

        snap = build_universe_v2_snapshot()
        return {
            "ok": True,
            "version": snap.version,
            "status": snap.status,
            "research_pool_count": snap.research_pool_count,
            "created_at_utc": snap.created_at_utc,
        }
    except Exception as e:  # fail-closed; never crash the API
        logger.exception("[UNIVERSE_V2] refresh failed: %s", e)
        raise HTTPException(status_code=500, detail="universe-v2 refresh failed")
