#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""View decision dashboard (Phase 6A).

⚠️ DEPRECATED: This script is deprecated in favor of scripts/live_dashboard.py (Phase 7).
This file is kept for backward compatibility but should not be used for new development.
Use scripts/live_dashboard.py instead.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.ui.decision_dashboard import (
    FASTAPI_AVAILABLE,
    generate_dashboard_html,
    run_dashboard,
)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="View decision dashboard")
    parser.add_argument(
        "json_file",
        type=str,
        help="Path to decision JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output HTML file (for static generation, default: same name as JSON with .html)",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run as web server (requires FastAPI)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"ERROR: JSON file not found: {json_path}")
        return 1

    if args.server:
        if not FASTAPI_AVAILABLE:
            print("ERROR: FastAPI not available. Install with: pip install fastapi uvicorn")
            return 1
        run_dashboard(str(json_path), host=args.host, port=args.port)
    else:
        output_path = generate_dashboard_html(str(json_path), args.output)
        print(f"\nDashboard generated: {output_path}")
        print(f"Open in browser: file://{output_path.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
