# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Secured UI API: /api/ui/* — minimal surface for React frontend. LIVE vs MOCK separation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Header, HTTPException, Query

from app.ui.live_dashboard_utils import list_decision_files, list_mock_files, load_decision_artifact

router = APIRouter(prefix="/api/ui", tags=["ui"])

UI_API_KEY = (os.getenv("UI_API_KEY") or "").strip()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        return Path(get_output_dir())
    except Exception:
        return _repo_root() / "out"


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    """If UI_API_KEY is set, require x-ui-key header. Otherwise allow (local dev)."""
    if not UI_API_KEY:
        return
    key = (x_ui_key or "").strip()
    if key != UI_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


def _validate_live_artifact(data: Dict[str, Any]) -> None:
    """LIVE mode: reject artifacts with data_source in (mock, scenario)."""
    ds = (data.get("data_source") or data.get("metadata", {}).get("data_source") or "").strip().lower()
    if ds in ("mock", "scenario"):
        raise HTTPException(
            status_code=400,
            detail=f"LIVE mode must not load mock/scenario data (data_source={ds})",
        )


Mode = Literal["LIVE", "MOCK"]


@router.get("/decision/files")
def ui_decision_files(
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    List decision files for the given mode.
    LIVE: out/ only; exclude decision_MOCK.json; exclude out/mock.
    MOCK: out/mock only.
    """
    _require_ui_key(x_ui_key)
    out_base = _output_dir()
    if mode == "LIVE":
        infos = list_decision_files(out_base, exclude_mock=True)
        out_dir = str(out_base)
    else:
        mock_dir = out_base / "mock"
        infos = list_mock_files(mock_dir)
        out_dir = str(mock_dir)

    files: List[Dict[str, Any]] = []
    for f in infos:
        try:
            mtime = datetime.fromtimestamp(f.modified_epoch_s, tz=timezone.utc)
            mtime_iso = mtime.isoformat()
        except (OSError, ValueError):
            mtime_iso = ""
        try:
            size = f.path.stat().st_size
        except OSError:
            size = 0
        files.append({
            "name": f.path.name,
            "mtime_iso": mtime_iso,
            "size_bytes": size,
        })
    return {"mode": mode, "dir": out_dir, "files": files}


@router.get("/decision/latest")
def ui_decision_latest(
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get decision_latest.json content.
    LIVE: out/decision_latest.json; validates data_source.
    MOCK: out/mock/decision_latest.json; 404 if absent.
    """
    _require_ui_key(x_ui_key)
    out_base = _output_dir()
    if mode == "LIVE":
        path = out_base / "decision_latest.json"
    else:
        path = out_base / "mock" / "decision_latest.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No decision_latest.json for mode={mode}")

    data = load_decision_artifact(path)
    if mode == "LIVE":
        _validate_live_artifact(data)
    return data


@router.get("/decision/file/{filename}")
def ui_decision_file(
    filename: str,
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get a specific decision file. Filename must be in the list returned by /decision/files.
    Prevents path traversal.
    """
    _require_ui_key(x_ui_key)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if mode == "LIVE":
        out_dir = _output_dir()
        infos = list_decision_files(out_dir, exclude_mock=True)
    else:
        out_dir = _output_dir() / "mock"
        infos = list_mock_files(out_dir)
    allowed = {f.path.name for f in infos}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail=f"File not found for mode={mode}")

    path = out_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    data = load_decision_artifact(path)
    if mode == "LIVE":
        _validate_live_artifact(data)
    return data


@router.get("/universe")
def ui_universe(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """UI-friendly universe snapshot: source, updated_at, as_of, symbols with key fields."""
    _require_ui_key(x_ui_key)
    from app.api.data_health import fetch_universe_from_canonical_snapshot
    from app.api.response_normalizers import normalize_universe_snapshot
    from app.market.market_hours import get_market_phase

    phase = get_market_phase()
    try:
        if phase == "OPEN":
            result = fetch_universe_from_canonical_snapshot()
            if result.get("all_failed"):
                return {
                    "source": "LIVE_COMPUTE",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "symbols": [],
                }
            out = normalize_universe_snapshot({**result, "error": None, "source": "LIVE_COMPUTE"})
        else:
            from app.core.eval.run_artifacts import build_universe_from_latest_artifact
            artifact = build_universe_from_latest_artifact()
            if artifact:
                out = normalize_universe_snapshot({**artifact, "error": None, "source": "ARTIFACT_LATEST"})
            else:
                result = fetch_universe_from_canonical_snapshot()
                out = normalize_universe_snapshot({**result, "error": None, "source": "LIVE_COMPUTE_NO_ARTIFACT"})
    except Exception as e:
        return {
            "source": "LIVE_COMPUTE",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "symbols": [],
            "error": str(e),
        }

    updated = out.get("updated_at") or datetime.now(timezone.utc).isoformat()
    return {
        "source": out.get("source", "UNKNOWN"),
        "updated_at": updated,
        "as_of": updated,
        "symbols": out.get("symbols", []),
    }


@router.get("/symbol-diagnostics")
def ui_symbol_diagnostics(
    symbol: str = Query(..., min_length=1, max_length=12),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """UI-friendly symbol diagnostics: primary_reason, key fields, stage breakdown."""
    _require_ui_key(x_ui_key)
    from app.api.symbol_diagnostics import get_symbol_diagnostics

    result = get_symbol_diagnostics(symbol=symbol)
    return {
        "symbol": result.get("symbol"),
        "primary_reason": result.get("eligibility", {}).get("primary_reason"),
        "verdict": result.get("eligibility", {}).get("verdict"),
        "in_universe": result.get("in_universe"),
        "stock": result.get("stock"),
        "gates": result.get("gates", []),
        "blockers": result.get("blockers", []),
        "notes": result.get("notes", []),
    }
