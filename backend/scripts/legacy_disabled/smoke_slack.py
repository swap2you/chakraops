#!/usr/bin/env python3
"""Simple smoke test for Slack notifications."""

from __future__ import annotations

import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from app.notify.slack import send_slack


def main() -> int:
    """Send a test message to Slack."""
    try:
        send_slack("ChakraOps Slack test OK")
        print("Slack message sent successfully", file=sys.stdout)
        return 0
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
