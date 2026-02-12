#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 4: Refresh ORATS contract test fixtures from live API.

Run manually when ORATS response shape or sample data should be updated.
Requires ORATS_API_TOKEN in .env. Writes to tests/fixtures/orats/.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Repo root = parent of chakraops
REPO_ROOT = Path(__file__).resolve().parents[1]
CHAKRAOPS = REPO_ROOT / "chakraops"
FIXTURES_DIR = CHAKRAOPS / "tests" / "fixtures" / "orats"


def _load_env():
    env_file = CHAKRAOPS / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    _load_env()
    token = os.getenv("ORATS_API_TOKEN")
    if not token:
        print("ORATS_API_TOKEN not set. Add to .env or export.", file=sys.stderr)
        return 1

    sys.path.insert(0, str(CHAKRAOPS))

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    tickers = ["AAPL", "SPY"]
    try:
        from app.core.orats.orats_equity_quote import _extract_rows
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        return 1

    import requests
    from app.core.orats.orats_equity_quote import (
        ORATS_BASE_URL,
        ORATS_STRIKES_OPTIONS_PATH,
        ORATS_IVRANK_PATH,
    )
    url = f"{ORATS_BASE_URL}{ORATS_STRIKES_OPTIONS_PATH}"
    params = {"token": token, "tickers": ",".join(tickers)}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    raw = r.json()
    rows = _extract_rows(raw)
    underlying = [row for row in rows if not row.get("optionSymbol")]
    out_path = FIXTURES_DIR / "orats_strikes_options_underlying.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(underlying[:4], f, indent=2)
    print(f"Wrote {out_path} ({len(underlying[:4])} rows)")

    # 2) Fetch /datav2/ivrank
    url_iv = f"{ORATS_BASE_URL}{ORATS_IVRANK_PATH}"
    params_iv = {"token": token, "ticker": ",".join(tickers)}
    r2 = requests.get(url_iv, params=params_iv, timeout=15)
    r2.raise_for_status()
    raw_iv = r2.json()
    rows_iv = _extract_rows(raw_iv)
    out_iv = FIXTURES_DIR / "orats_ivrank.json"
    with open(out_iv, "w", encoding="utf-8") as f:
        json.dump(rows_iv[:4], f, indent=2)
    print(f"Wrote {out_iv} ({len(rows_iv[:4])} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
