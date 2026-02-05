#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Launch the live decision dashboard.

Convenience wrapper: runs ONLY Streamlit. It does NOT trigger pipeline runs.
STRICT: Read-only; reads decision_*.json from disk.
To generate decision_*.json on a schedule, run scripts.run_pipeline_loop instead.
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
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy dashboard instead of premium UI",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    
    # Use premium dashboard by default, legacy with --legacy flag
    if args.legacy:
        app_path = repo_root / "app" / "ui" / "live_decision_dashboard.py"
    else:
        app_path = repo_root / "app" / "ui" / "premium_dashboard.py"
    
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
    print(f"  Mode: {'Legacy' if args.legacy else 'Premium'}", file=sys.stderr)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

