#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS sanity check: token, health, and one symbol expirations. No secrets in output."""

from __future__ import annotations

import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

# Load .env so ORATS_API_TOKEN is available
from dotenv import load_dotenv
load_dotenv(repo_root / ".env")


def main() -> int:
    token = (os.getenv("ORATS_API_TOKEN") or "").strip()
    if not token:
        print("ORATS_API_TOKEN is not set. Set it to run ORATS sanity check.")
        return 1

    print("ORATS_API_TOKEN: set (length %d)" % len(token))
    print("Checking ORATS connectivity...")

    try:
        from app.core.options.providers.orats_provider import OratsOptionsChainProvider
        provider = OratsOptionsChainProvider()
        status = provider.healthcheck()
        ok = status.get("ok", False)
        msg = status.get("message", "Unknown")
        if not ok:
            print("ORATS health check failed:", msg)
            return 1
        print("ORATS health:", msg)

        print("Fetching AAPL expirations...")
        expirations = provider.get_expirations("AAPL")
        if not expirations:
            print("No expirations for AAPL (empty response or auth/rate limit).")
            return 1
        print("AAPL expirations: %d" % len(expirations))
        print("First 3:", [d.isoformat() for d in expirations[:3]])

        # OptionContext for AAPL and MSFT (Sub-Phase 3.1)
        for sym in ("AAPL", "MSFT"):
            try:
                ctx = provider.get_option_context(sym)
                print("\nOptionContext %s:" % sym)
                print("  expected_move_1sd: %s" % ctx.expected_move_1sd)
                print("  iv_rank: %s  iv_percentile: %s" % (ctx.iv_rank, ctx.iv_percentile))
                print("  term_structure_slope: %s  skew_metric: %s" % (ctx.term_structure_slope, ctx.skew_metric))
                print("  days_to_earnings: %s  event_flags: %s" % (ctx.days_to_earnings, ctx.event_flags))
            except Exception as e:
                print("\nOptionContext %s failed: %s" % (sym, e))

        print("\nORATS sanity check OK.")
        return 0
    except Exception as e:
        print("ORATS sanity check failed:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
