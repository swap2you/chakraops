#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
EOD freeze snapshot: copy decision_latest.json to decision_frozen.json atomically.
After market close, UI/API serve from decision_frozen.json until next open.
Exit: 0 success, 2 validation fail (missing latest or not v2), 3 runtime error.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
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
        from app.core.eval.evaluation_store_v2 import get_decision_store_path, _frozen_path

        latest_path = get_decision_store_path()
        frozen_path = _frozen_path()
        if not latest_path.exists():
            print("VALIDATION FAIL: decision_latest.json missing at", latest_path)
            return 2
        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("metadata") or {}
        if meta.get("artifact_version") != "v2":
            print("VALIDATION FAIL: artifact_version is not v2 at", latest_path)
            return 2
        pipeline_ts = meta.get("pipeline_timestamp") or ""

        # Atomic write: temp in same dir then replace
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=frozen_path.parent, prefix="decision_frozen.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, frozen_path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            raise

        # Optional metadata file
        meta_path = frozen_path.parent / "decision_frozen_meta.json"
        try:
            from zoneinfo import ZoneInfo
            et = ZoneInfo("America/New_York")
            now_et = datetime.now(et)
            now_utc = datetime.now(timezone.utc)
        except Exception:
            now_et = now_utc = datetime.now(timezone.utc)
        meta_content = {
            "frozen_at_et": now_et.isoformat(),
            "frozen_at_utc": now_utc.isoformat(),
            "pipeline_timestamp": pipeline_ts,
            "source_file": str(latest_path),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_content, f, indent=2)
        print(f"[EOD_FREEZE] wrote decision_frozen.json pipeline_timestamp={pipeline_ts}")
        return 0
    except Exception as e:
        print("RUNTIME ERROR:", e)
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
