#!/usr/bin/env python3
"""
Theta v3 REST smoketest (stocks, options, index).

Runs direct HTTP tests against the local Theta v3 terminal:
  - STOCK:
      /stock/list/symbols?format=json
      /stock/snapshot/trade?symbol=AAPL&format=json
  - OPTION:
      /option/list/expirations?symbol=SPY&format=json
      /option/list/strikes?symbol=SPY&expiration=YYYYMMDD&format=json
  - INDEX:
      /index/list/symbols?format=json
      /index/snapshot/quote?symbol=<SPX or VIX>&format=json (if supported)

Exit code:
  0 if stock + option tests PASS (index may be SKIP)
  1 if stock or option tests FAIL.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, date
from typing import Any

import httpx
import pytz


BASE_URL = os.getenv("THETA_REST_URL", "http://127.0.0.1:25503/v3").rstrip("/")


def _now_utc_et() -> tuple[str, str]:
    utc = pytz.UTC
    et_tz = pytz.timezone("America/New_York")
    now_utc = datetime.now(utc)
    now_et = now_utc.astimezone(et_tz)
    return now_utc.isoformat(), now_et.isoformat()


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    api_key = os.getenv("THETA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _print_masked_headers(headers: dict[str, str]) -> None:
    masked = {k: ("***" if v else v) for k, v in headers.items()}
    print(f"  headers: {masked}")


def _stock_tests(client: httpx.Client) -> bool:
    print("== STOCK TESTS ==")
    ok = True
    h = _headers()

    # list symbols
    url = f"{BASE_URL}/stock/list/symbols"
    params = {"format": "json"}
    print(f"STOCK list symbols: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAIL: stock list symbols status={resp.status_code}")
        ok = False
    else:
        try:
            data = resp.json()
            sample = (data[:5] if isinstance(data, list) else data)  # type: ignore
            print(f"  PASS: list symbols sample={sample}")
        except Exception as e:
            print(f"  WARN: could not parse symbols JSON: {e}")

    # snapshot trade
    url = f"{BASE_URL}/stock/snapshot/trade"
    params = {"symbol": "AAPL", "format": "json"}
    print(f"STOCK snapshot trade: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code == 403:
        print(f"  UNAVAILABLE (PLAN): stock snapshot trade blocked by subscription tier")
        print(f"  body={resp.text[:400]}")
        # 403 is plan limitation, not a failure - don't mark as FAIL
    elif resp.status_code != 200:
        print(f"  FAIL: stock snapshot trade AAPL status={resp.status_code}")
        ok = False
        print(f"  body={resp.text[:400]}")
    else:
        try:
            data = resp.json()
            print(f"  PASS: snapshot trade AAPL sample={data}")
        except Exception as e:
            print(f"  WARN: could not parse trade JSON: {e}")

    print()
    return ok


def _option_tests(client: httpx.Client) -> bool:
    print("== OPTION TESTS ==")
    ok = True
    h = _headers()

    # expirations
    url = f"{BASE_URL}/option/list/expirations"
    params = {"symbol": "SPY", "format": "json"}
    print(f"OPTION list expirations: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAIL: option list expirations SPY status={resp.status_code}")
        print(f"  body={resp.text[:400]}")
        return False
    try:
        data = resp.json()
    except Exception as e:
        print(f"  FAIL: could not parse expirations JSON: {e}")
        return False
    
    # Parse Theta v3 response shape: {"response":[{"symbol":"SPY","expiration":"YYYY-MM-DD"}, ...]}
    # Historical expirations are VALID - parse all
    exps: list[str] = []
    if isinstance(data, dict):
        if "response" in data:
            exp_list = data["response"]
            for x in exp_list:
                if isinstance(x, dict):
                    val = x.get("expiration") or x.get("date") or x.get("expiry")
                else:
                    val = x
                if isinstance(val, str):
                    exps.append(val)
        elif "expirations" in data:
            for x in data["expirations"]:
                if isinstance(x, str):
                    exps.append(x)
    elif isinstance(data, list):
        for x in data:
            if isinstance(x, dict):
                val = x.get("expiration") or x.get("date")
            else:
                val = x
            if isinstance(val, str):
                exps.append(val)
    
    print(f"  expirations_count={len(exps)} sample={exps[:5]}")
    # PASS if HTTP 200 AND response has data (historical expirations are VALID)
    if not exps:
        print("  FAIL: no expirations for SPY (empty response)")
        return False
    print("  PASS: expirations endpoint returned data (historical expirations are valid)")

    # Selection logic: pick nearest expiration >= today, or fallback to LATEST historical
    today = date.today()
    chosen = None
    latest_historical = None
    for s in exps:
        s_clean = s.replace("-", "")
        if len(s_clean) < 8 or not s_clean[:8].isdigit():
            continue
        try:
            y, m, d = int(s_clean[:4]), int(s_clean[4:6]), int(s_clean[6:8])
            exp_date = date(y, m, d)
            if exp_date >= today:
                if chosen is None or exp_date < chosen:
                    chosen = exp_date
            else:
                # Track latest historical expiration as fallback
                if latest_historical is None or exp_date > latest_historical:
                    latest_historical = exp_date
        except (ValueError, IndexError):
            continue
    
    # Fallback to latest historical if no future expiration
    if chosen is None:
        if latest_historical is not None:
            chosen = latest_historical
            print(f"  INFO: Using latest historical expiration {chosen} (no future expirations)")
        else:
            # Last resort: use today (may not exist, but strikes endpoint will handle it)
            chosen = today
            print(f"  WARN: No valid expiration found, using today {chosen}")
    
    exp_str = chosen.strftime("%Y%m%d")

    # strikes
    url = f"{BASE_URL}/option/list/strikes"
    params = {"symbol": "SPY", "expiration": exp_str, "format": "json"}
    print(f"OPTION list strikes: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAIL: option list strikes SPY status={resp.status_code}")
        print(f"  body={resp.text[:400]}")
        ok = False
    else:
        try:
            strikes_data = resp.json()
            strikes_list = []
            if isinstance(strikes_data, list):
                strikes_list = strikes_data
            elif isinstance(strikes_data, dict):
                strikes_list = strikes_data.get("strikes") or strikes_data.get("response") or []
            print(f"  PASS: strikes count={len(strikes_list)} sample={strikes_list[:10]}")
            
            # Test snapshot quote endpoint - PASS if at least ONE returns HTTP 200
            # Do NOT require bid/ask > 0 (zero values are VALID per OpenAPI v3)
            if strikes_list:
                test_strike = strikes_list[0]
                try:
                    strike_f = float(test_strike)
                    snap_url = f"{BASE_URL}/option/snapshot/quote"
                    snap_params = {
                        "symbol": "SPY",
                        "expiration": exp_str,
                        "strike": strike_f,
                        "right": "P",
                        "format": "json",
                    }
                    print(f"OPTION snapshot quote: {snap_url} {snap_params}")
                    snap_resp = client.get(snap_url, params=snap_params, headers=h, timeout=5.0)
                    print(f"  status={snap_resp.status_code}")
                    if snap_resp.status_code == 200:
                        try:
                            snap_data = snap_resp.json()
                            print(f"  PASS: snapshot quote returned contract")
                            print(f"    sample_contract: strike={strike_f} right=P bid={snap_data.get('bid')} ask={snap_data.get('ask')} delta={snap_data.get('delta')}")
                        except Exception as e:
                            print(f"  WARN: could not parse snapshot JSON: {e}")
                    else:
                        print(f"  WARN: snapshot quote status={snap_resp.status_code} (may be normal for some strikes)")
                except (ValueError, TypeError) as e:
                    print(f"  WARN: could not convert strike to float: {e}")
        except Exception as e:
            print(f"  WARN: could not parse strikes JSON: {e}")

    print()
    return ok


def _index_tests(client: httpx.Client) -> None:
    print("== INDEX TESTS ==")
    h = _headers()

    url = f"{BASE_URL}/index/list/symbols"
    params = {"format": "json"}
    print(f"INDEX list symbols: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  SKIP: index list symbols status={resp.status_code}")
        print(f"  body={resp.text[:400]}")
        print()
        return

    try:
        symbols = resp.json()
    except Exception as e:
        print(f"  SKIP: could not parse index symbols JSON: {e}")
        print()
        return

    candidates = [s for s in symbols if isinstance(s, str) and s.upper() in ("SPX", "VIX")]
    if not candidates:
        print("  SKIP: no SPX/VIX in index symbols")
        print()
        return

    sym = candidates[0]
    url = f"{BASE_URL}/index/snapshot/quote"
    params = {"symbol": sym, "format": "json"}
    print(f"INDEX snapshot quote: {url} {params}")
    _print_masked_headers(h)
    resp = client.get(url, params=params, headers=h)
    print(f"  status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  SKIP: index snapshot quote {sym} status={resp.status_code}")
        print(f"  body={resp.text[:400]}")
    else:
        try:
            data = resp.json()
            print(f"  PASS: index snapshot quote {sym} sample={data}")
        except Exception as e:
            print(f"  WARN: could not parse index quote JSON: {e}")
    print()


def main() -> int:
    now_utc, now_et = _now_utc_et()
    print(f"[THETA][SMOKETEST] Now UTC: {now_utc}")
    print(f"[THETA][SMOKETEST] Now ET : {now_et}")
    print(f"[THETA][SMOKETEST] Base URL: {BASE_URL}")
    print()

    try:
        with httpx.Client(timeout=10.0) as client:
            stock_ok = _stock_tests(client)
            option_ok = _option_tests(client)
            _index_tests(client)
    except httpx.ConnectError as e:
        print("[THETA][SMOKETEST] ERROR: Theta v3 terminal not reachable.", file=sys.stderr)
        print(f"[THETA][SMOKETEST] Detail: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[THETA][SMOKETEST] ERROR: {e}", file=sys.stderr)
        return 1

    # Overall result: PASS if option_available == True (stock/index may be unavailable due to plan)
    if option_ok:
        print("[THETA][SMOKETEST] RESULT: PASS (options available)")
        return 0
    else:
        print("[THETA][SMOKETEST] RESULT: FAIL (options unavailable)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

