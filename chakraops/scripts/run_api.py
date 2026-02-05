#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run ChakraOps REST API (Phase 10). Serves /api/market-status, /api/view/*, /api/ops/evaluate, /api/view/symbol-diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ChakraOps API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    args = parser.parse_args()
    try:
        import uvicorn
        from app.api.server import app
        uvicorn.run(app, host=args.host, port=args.port)
    except ImportError as e:
        print(f"ERROR: {e}. Install fastapi and uvicorn: pip install fastapi uvicorn", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
