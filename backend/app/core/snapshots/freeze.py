# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
EOD freeze snapshot — archival copy of persisted stores.
Creates out/snapshots/YYYY-MM-DD_eod/ with copies. NEVER read by runtime.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

logger = logging.getLogger(__name__)

FreezeMode = Literal["archive_only", "eval_then_archive"]


def _git_commit(repo_root: Path | None = None) -> str | None:
    """Return current git commit hash if available."""
    try:
        cwd = repo_root or (Path(__file__).resolve().parents[4])
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()[:12]
    except Exception:
        pass
    return None


def run_freeze_snapshot(
    out_dir: Path,
    decision_store_path: Path,
    extra_paths: List[Path],
    mode: FreezeMode,
    now_utc: datetime | None = None,
) -> Dict[str, Any]:
    """
    Archive persisted stores into out/snapshots/YYYY-MM-DD_eod/.
    mode: archive_only = just copy; eval_then_archive is handled by caller (run eval, then call with archive_only).
    Uses atomic manifest write (temp then rename).
    Skips missing files with note in manifest.
    Returns {snapshot_dir, manifest, copied_files}.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
    except Exception:
        et_tz = timezone.utc
    now_et = now_utc.astimezone(et_tz)
    date_str = now_et.strftime("%Y-%m-%d")
    snap_dir = out_dir / "snapshots" / f"{date_str}_eod"
    snap_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "created_at_utc": now_utc.isoformat(),
        "created_at_et": now_et.isoformat(),
        "git_commit": _git_commit(out_dir.parent.parent if "chakraops" in str(out_dir) else None),
        "mode": mode,
        "files": [],
        "skipped": [],
    }
    copied_files: List[str] = []

    def _copy_one(src: Path, dest_name: str) -> bool:
        if not src.exists():
            manifest["skipped"].append({"name": dest_name, "reason": "not found"})
            return False
        dst = snap_dir / dest_name
        try:
            shutil.copy2(src, dst)
            st = dst.stat()
            manifest["files"].append({
                "name": dest_name,
                "size_bytes": st.st_size,
                "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
            copied_files.append(dest_name)
            return True
        except Exception as e:
            manifest["skipped"].append({"name": dest_name, "reason": str(e)})
            return False

    # Decision store files (from same parent as decision_store_path)
    store_parent = decision_store_path.parent
    frozen_path = store_parent / "decision_frozen.json"
    _copy_one(decision_store_path, "decision_latest.json")
    _copy_one(frozen_path, "decision_frozen.json")

    # Extra paths (caller can add more)
    for p in extra_paths:
        if p.exists() and p.is_file():
            dest_name = p.name if p.name != "positions.json" or p.parent.name != "positions" else "positions.json"
            if dest_name not in copied_files:
                _copy_one(p, dest_name)

    # Standard paths relative to out_dir (copy if not already)
    standard = [
        (out_dir / "notifications.jsonl", "notifications.jsonl"),
        (out_dir / "diagnostics_history.jsonl", "diagnostics_history.jsonl"),
        (out_dir / "positions" / "positions.json", "positions.json"),
    ]
    for src, dest_name in standard:
        if dest_name not in copied_files:
            _copy_one(src, dest_name)

    # Atomic manifest write
    manifest_path = snap_dir / "snapshot_manifest.json"
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=snap_dir)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            Path(tmp_path).replace(manifest_path)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning("[FREEZE] Atomic manifest write failed, writing directly: %s", e)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    logger.info("[FREEZE] Created %s with %d files", snap_dir, len(copied_files))
    return {
        "snapshot_dir": str(snap_dir),
        "manifest": manifest,
        "copied_files": copied_files,
    }
