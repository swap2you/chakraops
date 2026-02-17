#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
EOD freeze snapshot — archival copy of persisted stores.
Creates out/snapshots/YYYY-MM-DD_eod/ with copies of notifications, diagnostics,
positions, and canonical decision store. NEVER read by runtime; archival only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO / ".env")
except ImportError:
    pass


def _git_commit() -> str | None:
    """Return current git commit hash if available."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()[:12]
    except Exception:
        pass
    return None


def main() -> int:
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
    except Exception:
        et_tz = timezone.utc

    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(et_tz)
    date_str = now_et.strftime("%Y-%m-%d")

    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out_dir = get_decision_store_path().parent
    except Exception:
        out_dir = _REPO.parent / "out"

    snap_dir = out_dir / "snapshots" / f"{date_str}_eod"
    snap_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_archive(out_dir, snap_dir, now_utc, now_et)
        return 0
    except Exception as e:
        print(f"[FREEZE_SNAPSHOT_ARCHIVE] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


def _run_archive(out_dir: Path, snap_dir: Path, now_utc: datetime, now_et: datetime) -> None:
    """Copy stores and write manifest."""
    manifest = {
        "created_at_utc": now_utc.isoformat(),
        "created_at_et": now_et.isoformat(),
        "git_commit": _git_commit(),
        "files": [],
    }

    # Copy notifications
    src = out_dir / "notifications.jsonl"
    if src.exists():
        dst = snap_dir / "notifications.jsonl"
        shutil.copy2(src, dst)
        st = dst.stat()
        manifest["files"].append({
            "name": "notifications.jsonl",
            "size_bytes": st.st_size,
            "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })

    # Copy diagnostics history
    src = out_dir / "diagnostics_history.jsonl"
    if src.exists():
        dst = snap_dir / "diagnostics_history.jsonl"
        shutil.copy2(src, dst)
        st = dst.stat()
        manifest["files"].append({
            "name": "diagnostics_history.jsonl",
            "size_bytes": st.st_size,
            "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })

    # Copy positions
    pos_dir = out_dir / "positions"
    pos_file = pos_dir / "positions.json"
    if pos_file.exists():
        dst = snap_dir / "positions.json"
        shutil.copy2(pos_file, dst)
        st = dst.stat()
        manifest["files"].append({
            "name": "positions.json",
            "size_bytes": st.st_size,
            "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })

    # Copy canonical decision store
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path, _frozen_path
        latest = get_decision_store_path()
        frozen = _frozen_path()
        for p, name in [(latest, "decision_latest.json"), (frozen, "decision_frozen.json")]:
            if p.exists():
                dst = snap_dir / name
                shutil.copy2(p, dst)
                st = dst.stat()
                manifest["files"].append({
                    "name": name,
                    "size_bytes": st.st_size,
                    "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                })
    except Exception:
        # Fallback: copy out/decision_latest.json if present
        for name in ("decision_latest.json", "decision_frozen.json"):
            p = out_dir / name
            if p.exists():
                dst = snap_dir / name
                shutil.copy2(p, dst)
                st = dst.stat()
                manifest["files"].append({
                    "name": name,
                    "size_bytes": st.st_size,
                    "last_modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                })

    manifest_path = snap_dir / "snapshot_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[FREEZE_SNAPSHOT_ARCHIVE] Created {snap_dir}")
    print(f"[FREEZE_SNAPSHOT_ARCHIVE] Files: {[f['name'] for f in manifest['files']]}")


if __name__ == "__main__":
    sys.exit(main())
