#!/usr/bin/env python3
"""
Standalone Theta SPY expirations debug script.

Goal:
- Prove definitively whether Theta returns options expirations for SPY
  using the SAME base URL / creds as the app.
- No app abstractions, no snapshot logic, no caching.

Behavior:
- Loads THETA_REST_URL (and any auth-related env) exactly as the app would.
- Calls Theta's expirations endpoint directly for SPY.
- Prints:
  - Now (UTC and ET)
  - Full URL
  - HTTP status
  - Masked headers
  - Raw response text
All timestamps shown in America/New_York (ET).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import httpx
import pytz


def _now_utc_et() -> tuple[str, str]:
    utc = pytz.UTC
    et_tz = pytz.timezone("America/New_York")
    now_utc = datetime.now(utc)
    now_et = now_utc.astimezone(et_tz)
    return now_utc.isoformat(), now_et.isoformat()


def main() -> int:
    now_utc, now_et = _now_utc_et()
    base_url = (os.getenv("THETA_REST_URL", "http://127.0.0.1:25503/v3")).rstrip("/")
    symbol = "SPY"

    print(f"[THETA][DEBUG] Now UTC: {now_utc}")
    print(f"[THETA][DEBUG] Now ET : {now_et}")
    print(f"[THETA][DEBUG] Base URL: {base_url}")
    print(f"[THETA][DEBUG] Symbol : {symbol}")
    print()

    # Construct expirations endpoint exactly like the app-level provider
    # v3: /option/list/expirations?symbol=SPY&format=json
    path = "/option/list/expirations"
    url = f"{base_url}{path}"
    params = {"symbol": symbol, "format": "json"}

    # Load any auth headers / tokens if used (mask secrets in output)
    headers: dict[str, str] = {}
    # Example: if you use THETA_API_KEY or similar, wire it here.
    api_key = os.getenv("THETA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    masked_headers = {k: ("***" if v else v) for k, v in headers.items()}

    print(f"[THETA][DEBUG] Request URL    : {url}")
    print(f"[THETA][DEBUG] Request params : {params}")
    print(f"[THETA][DEBUG] Request headers: {masked_headers}")
    print()

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params, headers=headers)
    except Exception as e:
        print(f"[THETA][DEBUG] ERROR: request failed: {e}", file=sys.stderr)
        return 1

    print(f"[THETA][DEBUG] HTTP status    : {resp.status_code}")
    print(f"[THETA][DEBUG] Response headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    print()

    print("[THETA][DEBUG] Raw response body:")
    try:
        print(resp.text)
    except Exception as e:
        print(f"[THETA][DEBUG] ERROR printing body: {e}", file=sys.stderr)

    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())

