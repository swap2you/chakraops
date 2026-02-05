#!/usr/bin/env python3
# ORATS LIVE DATA HARD VERIFICATION — truth source. No abstractions.
# Run: python scripts/orats_smoke_test.py
# Requires: ORATS_API_KEY or ORATS_API_TOKEN, optional ORATS_API_BASE

import os
import sys
import time
from pathlib import Path

# Allow running from repo root or chakraops
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# Optional: load .env
try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass

BASE = (os.getenv("ORATS_API_BASE") or "https://api.orats.io").rstrip("/")
KEY = (os.getenv("ORATS_API_KEY") or os.getenv("ORATS_API_TOKEN") or "").strip()

if not KEY:
    print("ORATS_API_KEY (or ORATS_API_TOKEN) missing")
    sys.exit(1)

# api.orats.io uses ?ticker=SPY&token=KEY; api.orats.com may use path + Bearer
if "orats.io" in BASE:
    url = f"{BASE}/summaries"
    params = {"ticker": "SPY"}
    headers = {}
    # Token as query param for orats.io
    params["token"] = KEY
else:
    url = f"{BASE}/datav2/live/summaries/SPY.json"
    params = {}
    headers = {"Authorization": f"Bearer {KEY}"}

print("HITTING:", url, "(params redacted)")
t0 = time.time()
try:
    r = requests.get(url, params=params, headers=headers, timeout=15)
except Exception as e:
    print("STATUS: request failed")
    print("LATENCY:", round(time.time() - t0, 2), "sec")
    print("BODY:", str(e)[:500])
    print("ORATS LIVE DATA FAILED")
    print("===== ORATS FINAL VERDICT: FAIL =====")
    sys.exit(1)

dt = round(time.time() - t0, 2)
body_preview = (r.text or "")[:1000].replace(KEY, "[REDACTED]") if KEY in (r.text or "") else (r.text or "")[:1000]

print("STATUS:", r.status_code)
print("LATENCY:", dt, "sec")
print("BODY:", body_preview)

if r.status_code != 200:
    print("ORATS LIVE DATA FAILED")
    print("===== ORATS FINAL VERDICT: FAIL =====")
    sys.exit(1)

try:
    data = r.json()
except Exception:
    print("ORATS LIVE DATA FAILED (invalid JSON)")
    print("===== ORATS FINAL VERDICT: FAIL =====")
    sys.exit(1)

# Accept list (orats.io) or dict with data/price
has_price = False
if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
    first = data[0]
    has_price = any(first.get(k) is not None for k in ("stockPrice", "closePrice", "close", "underlyingPrice", "price"))
elif isinstance(data, dict):
    if "price" in data or "underlyingPrice" in data:
        has_price = True
    elif "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
        first = data["data"][0]
        has_price = any(first.get(k) is not None for k in ("stockPrice", "closePrice", "close", "underlyingPrice", "price"))

if not has_price:
    print("No price in ORATS response")
    print("ORATS LIVE DATA FAILED")
    print("===== ORATS FINAL VERDICT: FAIL =====")
    sys.exit(1)

print("ORATS LIVE DATA CONFIRMED")
print("===== ORATS FINAL VERDICT: PASS =====")
sys.exit(0)
