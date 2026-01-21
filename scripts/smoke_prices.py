
#!/usr/bin/env python3
"""Simple smoke test for Polygon daily prices."""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from app.data.polygon_provider import PolygonProvider


def main() -> int:
    try:
        provider = PolygonProvider()
        df = provider.get_daily("SPY")
    except Exception as exc:  # broad for quick smoke testing
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1

    print(df.tail(5))
    return 0


if __name__ == "__main__":
    sys.exit(main())