#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Launch the live (persistent) decision dashboard (Phase 7 Step 1).

This is a convenience wrapper around Streamlit.

STRICT: Read-only dashboard. It only reads JSON artifacts from disk.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ChakraOps live decision dashboard")
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port for Streamlit server (default: 8501)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    app_path = repo_root / "app" / "ui" / "live_decision_dashboard.py"
    if not app_path.exists():
        print(f"ERROR: Dashboard app not found: {app_path}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(args.port),
    ]

    print("Starting live dashboard (Streamlit)...", file=sys.stderr)
    print(f"  App: {app_path}", file=sys.stderr)
    print(f"  Port: {args.port}", file=sys.stderr)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

