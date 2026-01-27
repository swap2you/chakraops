#!/usr/bin/env python3
"""
Phase 2: ThetaData capability exploration. This tool is for learning only and
not part of the live trading pipeline.

Queries Theta REST (http://127.0.0.1:25503/v3) to discover what can be relied on
for real-time strategy work: stock last price, option snapshot OHLC, Greeks
(delta, gamma, theta, vega, iv), volume/open interest, and index support
(SPY, QQQ, SPX). Uses CSV only. Defensive to schema changes and 4xx/empty.
No DB writes, no app imports, tools/ only.
"""

import csv
import io
import sys
from datetime import date, timedelta
from typing import Any

import httpx

# --- Config (no app imports) ---
BASE_URL = "http://127.0.0.1:25503/v3"
TIMEOUT = 15.0
STOCK_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
INDEX_CHECK = ["SPX", "SPY", "QQQ"]  # order for output: SPX=... SPY=... QQQ=...
OPTION_ROOT = "SPY"
OPTION_STRIKE_1_10_CENT = 50000  # 500.00
OPTION_RIGHT = "C"


def _next_friday_yyyymmdd() -> str:
    d = date.today()
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d.strftime("%Y%m%d")


def _req_csv(client: httpx.Client, path: str, params: dict[str, Any]) -> str:
    p = dict(params)
    p["format"] = "csv"
    p["use_csv"] = "true"
    r = client.get(path, params=p, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def _parse_csv(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    try:
        for raw in csv.reader(io.StringIO(text)):
            rows.append(raw)
    except csv.Error as e:
        print(f"[THETA] csv parse error: {e}", file=sys.stderr)
    return rows


def _pick(row: list[str], header: list[str], *names: str) -> tuple[Any, ...]:
    out: list[Any] = []
    for name in names:
        nlo = name.lower()
        idx = next((i for i, h in enumerate(header) if (h or "").strip().lower() == nlo), -1)
        if 0 <= idx < len(row):
            v = row[idx].strip()
            if nlo in ("open", "high", "low", "close", "volume", "count", "delta", "gamma", "theta", "vega", "implied_vol", "iv", "bid", "ask"):
                try:
                    out.append(float(v) if v else None)
                except (ValueError, TypeError):
                    out.append(None)
            else:
                out.append(v if v else None)
        else:
            out.append(None)
    return tuple(out)


def _header_or_default(rows: list[list[str]], default: list[str]) -> tuple[list[str], int]:
    if not rows:
        return default[:], 0
    first = [c.strip() for c in rows[0]]
    looks_like_header = any(h and not h.replace(".", "").isdigit() for h in first)
    if looks_like_header:
        return first, 1
    return default[: len(first)], 0


def _log_schema_mismatch(row: list[str], header: list[str], label: str) -> None:
    if len(row) != len(header):
        print(f"[THETA] schema: {label} row_len={len(row)} header_len={len(header)} raw_row={row[:12]}", file=sys.stderr)


def run() -> int:
    print("[THETA] ThetaData capability explorer (Phase 2)")
    print("[THETA] Base URL:", BASE_URL)
    print()

    cap = {"stocks": "NO", "options_ohlc": "NO", "greeks": "NO", "iv": "NO", "oi": "NO"}
    index_support: dict[str, str] = {s: "NO" for s in INDEX_CHECK}
    exp_yyyymmdd = _next_friday_yyyymmdd()
    exp_display = f"{exp_yyyymmdd[:4]}-{exp_yyyymmdd[4:6]}-{exp_yyyymmdd[6:8]}"

    try:
        with httpx.Client(base_url=BASE_URL) as client:
            # --- (a) Stock last price (baseline) ---
            for symbol in STOCK_SYMBOLS:
                try:
                    text = _req_csv(client, "/stock/snapshot/trade", {"symbol": symbol})
                except httpx.HTTPStatusError:
                    try:
                        today = date.today().strftime("%Y%m%d")
                        text = _req_csv(client, "/stock/history/eod", {"symbol": symbol, "start_date": today, "end_date": today})
                    except (httpx.HTTPStatusError, httpx.RequestError):
                        print(f"[THETA] symbol={symbol} price=(skip)", file=sys.stderr)
                        continue
                except httpx.RequestError as e:
                    print(f"[THETA] symbol={symbol} request failed: {e}", file=sys.stderr)
                    continue
                rows = _parse_csv(text)
                if not rows:
                    print(f"[THETA] symbol={symbol} price=(no rows)")
                    continue
                header, data_start = _header_or_default(rows, ["ms_of_day", "price", "date"])
                for row in rows[data_start:]:
                    if not row:
                        continue
                    _log_schema_mismatch(row, header, "stock")
                    pcl = _pick(row, header, "price", "close", "last")
                    price = pcl[0] or pcl[1] or pcl[2]
                    if price is None and len(row) >= 2:
                        try:
                            price = float(row[1])
                        except (ValueError, TypeError):
                            pass
                    if price is not None:
                        cap["stocks"] = "OK"
                        print(f"[THETA] symbol={symbol} price={price:.2f}")
                    else:
                        print(f"[THETA] symbol={symbol} price=(missing)")
                    break
            print()

            # --- (b) Option snapshot OHLC ---
            ohlc_ok = False
            vol_from_ohlc: Any = None
            for path in ["/option/snapshot/ohlc", "/option/bulk_snapshot/ohlc", "/bulk_snapshot/option/ohlc"]:
                try:
                    params: dict[str, Any] = {"root": OPTION_ROOT, "exp": exp_yyyymmdd, "right": OPTION_RIGHT, "strike": OPTION_STRIKE_1_10_CENT}
                    if "bulk" in path:
                        params = {"root": OPTION_ROOT, "exp": exp_yyyymmdd}
                    text = _req_csv(client, path, params)
                except (httpx.HTTPStatusError, httpx.RequestError):
                    continue
                rows = _parse_csv(text)
                if not rows:
                    continue
                header, data_start = _header_or_default(rows, ["ms_of_day", "open", "high", "low", "close", "volume", "count", "date"])
                for row in rows[data_start:]:
                    if not row:
                        continue
                    _log_schema_mismatch(row, header, "option_ohlc")
                    close_val = _pick(row, header, "close")[0]
                    vol_val = _pick(row, header, "volume")[0]
                    if close_val is not None:
                        ohlc_ok = True
                        cap["options_ohlc"] = "OK"
                        vol_from_ohlc = vol_val
                    strike_display = OPTION_STRIKE_1_10_CENT / 1000.0
                    print(f"[THETA] option={OPTION_ROOT} {exp_display} {OPTION_RIGHT} {strike_display:.0f} close={close_val} volume={vol_from_ohlc}")
                    break
                if ohlc_ok:
                    break
            if not ohlc_ok:
                print(f"[THETA] option={OPTION_ROOT} (no option OHLC data)")
            print()

            # --- (c) Option Greeks (delta, theta, vega, iv) ---
            greeks_ok = False
            iv_ok = False
            for path in ["/bulk_snapshot/option/greeks", "/option/bulk_snapshot/greeks"]:
                try:
                    text = _req_csv(client, path, {"root": OPTION_ROOT, "exp": exp_yyyymmdd})
                except (httpx.HTTPStatusError, httpx.RequestError):
                    continue
                rows = _parse_csv(text)
                if not rows:
                    continue
                # Greeks schema: ms_of_day, bid, ask, delta, theta, vega, rho, epsilon, lambda, implied_vol, iv_error, ...
                header, data_start = _header_or_default(rows, ["ms_of_day", "bid", "ask", "delta", "theta", "vega", "rho", "epsilon", "lambda", "implied_vol", "iv_error", "ms_of_day2", "underlying_price", "date"])
                for row in rows[data_start:]:
                    if not row:
                        continue
                    _log_schema_mismatch(row, header, "greeks")
                    delta = _pick(row, header, "delta")[0]
                    theta = _pick(row, header, "theta")[0]
                    vega = _pick(row, header, "vega")[0]
                    iv = _pick(row, header, "implied_vol", "iv")[0] or _pick(row, header, "implied_vol", "iv")[1]
                    if delta is not None or theta is not None or vega is not None:
                        greeks_ok = True
                        cap["greeks"] = "OK"
                    if iv is not None:
                        iv_ok = True
                        cap["iv"] = "OK"
                    print(f"[THETA] option={OPTION_ROOT} {exp_display} {OPTION_RIGHT} {OPTION_STRIKE_1_10_CENT/1000:.0f} delta={delta} iv={iv}")
                    break
                if greeks_ok or iv_ok:
                    break
            if not greeks_ok and not iv_ok:
                print(f"[THETA] option={OPTION_ROOT} (no greeks/iv data)")
            print()

            # --- (d) Volume (from OHLC) and Open Interest ---
            if vol_from_ohlc is not None:
                print(f"[THETA] volume from OHLC: {vol_from_ohlc}")
            # OI: try common column names in options/greeks responses
            for path in ["/bulk_snapshot/option/greeks", "/option/bulk_snapshot/ohlc"]:
                try:
                    text = _req_csv(client, path, {"root": OPTION_ROOT, "exp": exp_yyyymmdd})
                except (httpx.HTTPStatusError, httpx.RequestError):
                    continue
                rows = _parse_csv(text)
                if not rows:
                    continue
                header, _ = _header_or_default(rows, [])
                hlo = [h.lower() for h in header]
                if "open_interest" in hlo or "oi" in hlo or "open interest" in str(hlo):
                    cap["oi"] = "OK"
                    break
            if cap["oi"] == "NO":
                print("[THETA] oi: not found in sampled endpoints")
            print()

            # --- (e) Index support: SPX, SPY, QQQ ---
            for sym in INDEX_CHECK:
                try:
                    _req_csv(client, "/stock/snapshot/trade", {"symbol": sym})
                    index_support[sym] = "YES"
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404 or (e.response.text and "subscription" in (e.response.text or "").lower()):
                        index_support[sym] = "NO"
                    else:
                        try:
                            today = date.today().strftime("%Y%m%d")
                            _req_csv(client, "/stock/history/eod", {"symbol": sym, "start_date": today, "end_date": today})
                            index_support[sym] = "YES"
                        except (httpx.HTTPStatusError, httpx.RequestError):
                            index_support[sym] = "NO"
                except httpx.RequestError:
                    index_support[sym] = "NO"
            parts = [f"{k}={v}" for k, v in index_support.items()]
            print(f"[THETA] index_support: {' '.join(parts)}")
            print()

            # --- Capabilities summary ---
            print("[THETA] capabilities summary:")
            print(f"  - stocks: {cap['stocks']}")
            print(f"  - options_ohlc: {cap['options_ohlc']}")
            print(f"  - greeks: {cap['greeks']}")
            print(f"  - iv: {cap['iv']}")
            print(f"  - oi: {cap['oi']}")
            print()
            print("[THETA] capability explorer done")
            return 0

    except httpx.ConnectError as e:
        print("[THETA] ERROR: Theta Terminal is not running or not reachable.", file=sys.stderr)
        print("[THETA] Start ThetaTerminal v3 on port 25503 (see docs/RUNBOOK_EXECUTION.md).", file=sys.stderr)
        print(f"[THETA] Detail: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[THETA] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
