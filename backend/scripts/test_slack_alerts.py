#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Send test messages to all configured Phase 7.2 Slack webhooks. Run: python scripts/test_slack_alerts.py"""

from __future__ import annotations

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
    from app.core.alerts.slack_dispatcher import get_slack_config_status, is_slack_configured, test_all_webhooks

    print("===== SLACK TEST (Phase 7.2) =====")
    if not is_slack_configured():
        print("No webhooks configured. Set SLACK_WEBHOOK_CRITICAL/SIGNALS/HEALTH/DAILY in .env")
        return 1

    status = get_slack_config_status()
    for name, configured in status.items():
        print(f"  {name}: {'configured' if configured else 'missing'}")
    print("Sending test messages (no dedup)...")

    results = test_all_webhooks()
    ok = 0
    for event_type, sent in results.items():
        label = "sent" if sent else "failed/missing"
        print(f"  {event_type}: {label}")
        if sent:
            ok += 1
    print("=================================")
    print(f"Result: {ok}/{len(results)} webhooks delivered.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
