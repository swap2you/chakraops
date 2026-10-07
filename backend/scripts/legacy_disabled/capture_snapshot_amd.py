#!/usr/bin/env python3
"""Capture GET /api/ops/snapshot?symbol=AMD to artifacts/snapshot_AMD.json.

Run with API server up: uvicorn app.api.server:app --port 8000
Usage: python scripts/capture_snapshot_amd.py [--base http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture /api/ops/snapshot?symbol=AMD to artifacts/snapshot_AMD.json")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    url = f"{base}/api/ops/snapshot?symbol=AMD"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 1

    # Repo root: script in scripts/ -> parent is chakraops
    repo_root = Path(__file__).resolve().parent.parent
    artifacts = repo_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    out_file = artifacts / "snapshot_AMD.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
