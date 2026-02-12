# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Canonical run artifacts under artifacts/runs/.

Layout:
  artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/
    snapshot.json   - per-symbol snapshot subset (canonical for UI)
    evaluation.json  - full evaluation run
    summary.md       - human-readable summary
  artifacts/runs/latest.json  - pointer to latest run
  artifacts/runs/recent.json  - list of last 3 runs (paths / run_id)

Purge: runs older than keep_days (default 10) are deleted.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.eval.evaluation_store import EvaluationRunFull

logger = logging.getLogger(__name__)

# Run ID format: eval_YYYYMMDD_HHMMSS_shortuuid
_RUN_ID_PATTERN = re.compile(r"^eval_(\d{8})_(\d{6})_[a-f0-9]+$")

# Keep last N runs in "recent" manifest
RECENT_RUNS_COUNT = 3
# Purge runs older than this many days
PURGE_KEEP_DAYS = 10


def _artifacts_runs_root() -> Path:
    """Repository root: chakraops/ (from app/core/eval/run_artifacts.py -> parents[3])."""
    return Path(__file__).resolve().parents[3] / "artifacts" / "runs"


def _run_id_to_date_and_time(run_id: str) -> tuple[str, str]:
    """
    Parse run_id (eval_YYYYMMDD_HHMMSS_xxx) -> (YYYY-MM-DD, HHMMSS).
    Raises ValueError if run_id does not match.
    """
    m = _RUN_ID_PATTERN.match(run_id.strip())
    if not m:
        raise ValueError(f"run_id does not match eval_YYYYMMDD_HHMMSS_xxx: {run_id}")
    date_part = m.group(1)  # YYYYMMDD
    time_part = m.group(2)   # HHMMSS
    # YYYYMMDD -> YYYY-MM-DD
    date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    return date_str, time_part


def _run_dir_name(run_id: str) -> str:
    """Run folder name: run_YYYYMMDD_HHMMSSZ."""
    _, time_part = _run_id_to_date_and_time(run_id)
    date_part = run_id[5:13]  # after "eval_" -> YYYYMMDD
    return f"run_{date_part}_{time_part}Z"


def _get_run_dir(run_id: str, completed_at: Optional[str] = None) -> Path:
    """Get artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/ for this run_id."""
    root = _artifacts_runs_root()
    date_str, time_part = _run_id_to_date_and_time(run_id)
    run_folder = _run_dir_name(run_id)
    return root / date_str / run_folder


def _build_snapshot_payload(run: EvaluationRunFull) -> Dict[str, Any]:
    """
    Canonical snapshot for UI: one object per symbol (keyed by symbol).
    Each entry has Stage-1 fields + verdict and key display fields.
    """
    out: Dict[str, Any] = {
        "run_id": run.run_id,
        "completed_at": run.completed_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": {},
    }
    for s in run.symbols:
        sym = s.get("symbol") or "UNKNOWN"
        out["symbols"][sym] = {
            "symbol": sym,
            "price": s.get("price"),
            "bid": s.get("bid"),
            "ask": s.get("ask"),
            "volume": s.get("volume"),
            "quote_date": s.get("quote_date"),
            "iv_rank": s.get("iv_rank"),
            "verdict": s.get("verdict"),
            "score": s.get("score"),
            "fetched_at": s.get("fetched_at"),
        }
    return out


def _build_summary_md(run: EvaluationRunFull, run_dir_path: str) -> str:
    """Human-readable summary markdown."""
    lines = [
        f"# Evaluation Run: {run.run_id}",
        "",
        f"- **Started:** {run.started_at}",
        f"- **Completed:** {run.completed_at or 'N/A'}",
        f"- **Status:** {run.status}",
        f"- **Duration:** {run.duration_seconds:.1f}s",
        "",
        "## Counts",
        f"- Total: {run.total} | Evaluated: {run.evaluated} | Eligible: {run.eligible} | Shortlisted: {run.shortlisted}",
        f"- Stage1 pass: {run.stage1_pass} | Stage2 pass: {run.stage2_pass} | Holds: {run.holds} | Blocks: {run.blocks}",
        "",
        f"- **Artifact path:** `{run_dir_path}`",
        "",
    ]
    if run.regime or run.risk_posture:
        lines.append(f"Regime: {run.regime} | Risk: {run.risk_posture}")
        lines.append("")
    return "\n".join(lines)


def write_run_artifacts(run: EvaluationRunFull) -> Optional[Path]:
    """
    Write canonical artifacts for a completed run:
      artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/snapshot.json
      artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/evaluation.json
      artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/summary.md
    Only writes when run.status == "COMPLETED" and run.completed_at is set.
    Returns the run directory path if written, None otherwise.
    """
    if run.status != "COMPLETED" or not run.completed_at:
        logger.debug("[RUN_ARTIFACTS] Skip writing (status=%s, completed_at=%s)", run.status, run.completed_at)
        return None
    try:
        run_dir = _get_run_dir(run.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_dir_str = str(run_dir)

        snapshot_data = _build_snapshot_payload(run)
        with open(run_dir / "snapshot.json", "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2, default=str)
            f.flush()

        evaluation_data = asdict(run)
        with open(run_dir / "evaluation.json", "w", encoding="utf-8") as f:
            json.dump(evaluation_data, f, indent=2, default=str)
            f.flush()

        summary_md = _build_summary_md(run, run_dir_str)
        (run_dir / "summary.md").write_text(summary_md, encoding="utf-8")

        logger.info("[RUN_ARTIFACTS] Wrote run artifacts to %s", run_dir)
        return run_dir
    except Exception as e:
        logger.warning("[RUN_ARTIFACTS] Failed to write artifacts for %s: %s", run.run_id, e)
        return None


# ---------------------------------------------------------------------------
# Latest and recent manifests
# ---------------------------------------------------------------------------

@dataclass
class LatestManifest:
    run_id: str
    path: str
    completed_at: str


def _latest_manifest_path() -> Path:
    return _artifacts_runs_root() / "latest.json"


def _recent_manifest_path() -> Path:
    return _artifacts_runs_root() / "recent.json"


def write_latest_manifest(run_id: str, run_dir: Path, completed_at: str) -> None:
    """Write artifacts/runs/latest.json with run_id, path, completed_at."""
    root = _artifacts_runs_root()
    root.mkdir(parents=True, exist_ok=True)
    path_str = str(run_dir)
    data = {"run_id": run_id, "path": path_str, "completed_at": completed_at}
    p = _latest_manifest_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
    logger.debug("[RUN_ARTIFACTS] Wrote latest.json -> %s", path_str)


def update_recent_manifest(run_id: str, run_dir: Path, completed_at: str) -> None:
    """Append this run to recent list and keep only last RECENT_RUNS_COUNT."""
    root = _artifacts_runs_root()
    root.mkdir(parents=True, exist_ok=True)
    path_str = str(run_dir)
    entry = {"run_id": run_id, "path": path_str, "completed_at": completed_at}

    recent_path = _recent_manifest_path()
    existing: List[Dict[str, str]] = []
    if recent_path.exists():
        try:
            with open(recent_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning("[RUN_ARTIFACTS] Could not read recent.json: %s", e)
    new_list = [entry] + [e for e in existing if e.get("path") != path_str]
    new_list = new_list[:RECENT_RUNS_COUNT]
    with open(recent_path, "w", encoding="utf-8") as f:
        json.dump(new_list, f, indent=2)
        f.flush()
    logger.debug("[RUN_ARTIFACTS] Updated recent.json (%d entries)", len(new_list))


def update_latest_and_recent(run: EvaluationRunFull, run_dir: Optional[Path]) -> None:
    """
    After writing artifacts, update latest.json and recent.json.
    Call only when run is COMPLETED and run_dir was returned by write_run_artifacts.
    """
    if run_dir is None or run.status != "COMPLETED" or not run.completed_at:
        return
    completed_at = run.completed_at or ""
    write_latest_manifest(run.run_id, run_dir, completed_at)
    update_recent_manifest(run.run_id, run_dir, completed_at)


def purge_old_runs(keep_days: int = PURGE_KEEP_DAYS) -> int:
    """
    Delete run directories older than keep_days.
    Scans artifacts/runs/YYYY-MM-DD/ and removes run_* folders (and date dirs if empty)
    older than (today - keep_days). Returns number of run directories removed.
    """
    root = _artifacts_runs_root()
    if not root.exists():
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).date()
    removed = 0
    for date_dir in list(root.iterdir()):
        if not date_dir.is_dir():
            continue
        try:
            # date_dir.name is YYYY-MM-DD
            dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
            if dir_date >= cutoff:
                continue
        except ValueError:
            continue
        for run_folder in list(date_dir.iterdir()):
            if run_folder.is_dir() and run_folder.name.startswith("run_"):
                try:
                    for f in run_folder.iterdir():
                        f.unlink()
                    run_folder.rmdir()
                    removed += 1
                except OSError as e:
                    logger.warning("[RUN_ARTIFACTS] Failed to remove %s: %s", run_folder, e)
        try:
            if not any(date_dir.iterdir()):
                date_dir.rmdir()
        except OSError:
            pass
    if removed > 0:
        logger.info("[RUN_ARTIFACTS] Purged %d run directories older than %d days", removed, keep_days)
    return removed


def get_latest_run_dir() -> Optional[Path]:
    """Return Path to latest run directory if latest.json exists and path exists."""
    p = _latest_manifest_path()
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        path_str = data.get("path")
        if path_str:
            path = Path(path_str)
            if path.exists():
                return path
    except Exception as e:
        logger.debug("[RUN_ARTIFACTS] get_latest_run_dir: %s", e)
    return None


def build_latest_response_from_artifacts() -> Optional[Dict[str, Any]]:
    """
    Build the same response shape as evaluation_store.build_latest_response()
    by reading from artifacts/runs/latest run dir. Returns None if no artifacts.
    Single source of truth for /api/view/evaluation/latest when artifacts exist.
    """
    run_dir = get_latest_run_dir()
    if not run_dir:
        return None
    eval_path = run_dir / "evaluation.json"
    if not eval_path.exists():
        return None
    try:
        with open(eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("[RUN_ARTIFACTS] Failed to read evaluation.json: %s", e)
        return None
    status = data.get("status", "COMPLETED")
    if status != "COMPLETED":
        return None
    return {
        "has_completed_run": True,
        "run_id": data.get("run_id"),
        "started_at": data.get("started_at"),
        "completed_at": data.get("completed_at"),
        "status": status,
        "engine": data.get("engine", "staged"),
        "duration_seconds": data.get("duration_seconds", 0),
        "counts": {
            "total": data.get("total", 0),
            "evaluated": data.get("evaluated", 0),
            "eligible": data.get("eligible", 0),
            "shortlisted": data.get("shortlisted", 0),
        },
        "regime": data.get("regime"),
        "risk_posture": data.get("risk_posture"),
        "market_phase": data.get("market_phase"),
        "top_candidates": data.get("top_candidates", []),
        "symbols": data.get("symbols", []),
        "alerts_count": data.get("alerts_count", 0),
        "errors_count": len(data.get("errors", [])),
        "read_source": "artifacts",
        "correlation_id": data.get("correlation_id") or data.get("run_id"),
    }


__all__ = [
    "write_run_artifacts",
    "write_latest_manifest",
    "update_recent_manifest",
    "update_latest_and_recent",
    "purge_old_runs",
    "get_latest_run_dir",
    "build_latest_response_from_artifacts",
    "RECENT_RUNS_COUNT",
    "PURGE_KEEP_DAYS",
    "_artifacts_runs_root",
    "_get_run_dir",
]
