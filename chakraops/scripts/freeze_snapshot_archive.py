#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
EOD freeze snapshot — archival copy of persisted stores.
Calls app.core.snapshots.freeze.run_freeze_snapshot (no shell out).
Creates out/snapshots/YYYY-MM-DD_eod/. NEVER read by runtime; archival only.
"""

from __future__ import annotations

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


def main() -> int:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out_dir = get_decision_store_path().parent
        decision_path = get_decision_store_path()
    except Exception:
        out_dir = _REPO.parent / "out"
        decision_path = out_dir / "decision_latest.json"

    now_utc = datetime.now(timezone.utc)
    try:
        from app.core.snapshots.freeze import run_freeze_snapshot
        result = run_freeze_snapshot(
            out_dir=out_dir,
            decision_store_path=decision_path,
            extra_paths=[],
            mode="archive_only",
            now_utc=now_utc,
        )
        print(f"[FREEZE_SNAPSHOT_ARCHIVE] Created {result['snapshot_dir']}")
        print(f"[FREEZE_SNAPSHOT_ARCHIVE] Files: {result['copied_files']}")
        return 0
    except Exception as e:
        print(f"[FREEZE_SNAPSHOT_ARCHIVE] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
