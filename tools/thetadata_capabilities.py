#!/usr/bin/env python3
"""
Phase 2 / 2.5: ThetaData capability exploration and realtime health & freshness
validation. This tool is for learning only and not part of the live trading pipeline.

Queries Theta REST (http://127.0.0.1:25503/v3) to discover capabilities and
optionally validate freshness. Produces a normalized in-memory contract (future
contract only; not wired into the system). Uses CSV only. Defensive to 4xx/empty.
No DB writes, no app imports, tools/ only.
"""

import argparse
import csv
import io
import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

# --- Config (no app imports) ---
BASE_URL = "http://127.0.0.1:25503/v3"
TIMEOUT = 15.0
STOCK_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
INDEX_CHECK = ["SPX", "SPY", "QQQ"]
OPTION_ROOT = "SPY"
OPTION_STRIKE_1_10_CENT = 50000
OPTION_RIGHT = "C"

# Phase 2.5: freshness thresholds (configurable)
STOCK_QUOTE_MAX_AGE_SECONDS = 15
OPTION_DATA_MAX_AGE_SECONDS = 60
# UNKNOWN timestamps never PASS (handled in health logic)


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


def _log_schema_mismatch(row: list[str], header: list[str], label: str, json_mode: bool = False) -> None:
    if json_mode or len(row) == len(header):
        return
    print(f"[THETA] schema: {label} row_len={len(row)} header_len={len(header)} raw_row={row[:12]}", file=sys.stderr)


# --- Phase 2.5: freshness extraction ---
# ThetaData: date=YYYYMMDD, ms_of_day=milliseconds since midnight Eastern.
# Best-effort UTC: ET = UTC-5 (no DST). Only set when date + ms_of_day both present.
def _pick_val(row: list[str], header: list[str], *names: str) -> Optional[Any]:
    for name in names:
        nlo = name.lower()
        idx = next((i for i, h in enumerate(header) if (h or "").strip().lower() == nlo), -1)
        if 0 <= idx < len(row):
            v = row[idx].strip()
            return v if v else None
    return None


def _parse_utc_from_row(
    row: list[str],
    header: list[str],
    date_cols: tuple[str, ...] = ("date",),
    ms_cols: tuple[str, ...] = ("ms_of_day", "ms_of_day2"),
) -> Optional[datetime]:
    """Extract best-available UTC datetime. Returns None if date or time missing (UNKNOWN)."""
    date_str = _pick_val(row, header, *date_cols)
    ms_str = _pick_val(row, header, *ms_cols)
    if not date_str:
        return None
    try:
        yyyymmdd = int(date_str.replace("-", "").strip()[:8])
        d = date(yyyymmdd // 10000, (yyyymmdd % 10000) // 100, yyyymmdd % 100)
    except (ValueError, TypeError):
        return None
    if ms_str is not None:
        try:
            ms = int(float(ms_str))
            et_naive = datetime(d.year, d.month, d.day) + timedelta(milliseconds=ms)
            # ET = UTC-5 (no DST); UTC = ET + 5h
            utc_naive = et_naive + timedelta(hours=5)
            return utc_naive.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None  # only date or parse failure -> UNKNOWN


def _age_seconds(dt: Optional[datetime], now_utc: datetime) -> Optional[int]:
    if dt is None:
        return None
    delta = now_utc - dt
    return int(delta.total_seconds())


def _log(msg: str, json_mode: bool) -> None:
    if not json_mode:
        print(msg)


def _log_stderr(msg: str, json_mode: bool) -> None:
    if not json_mode:
        print(msg, file=sys.stderr)


def run(verbose: bool = False, json_mode: bool = False) -> tuple[dict[str, Any], int]:
    now_utc = datetime.now(timezone.utc)
    cap = {"stocks": "NO", "options_ohlc": "NO", "greeks": "NO", "iv": "NO", "oi": "NO"}
    index_support: dict[str, str] = {s: "NO" for s in INDEX_CHECK}
    stock_quote_ts: Optional[datetime] = None
    option_ohlc_ts: Optional[datetime] = None
    greeks_ts: Optional[datetime] = None
    exp_yyyymmdd = _next_friday_yyyymmdd()
    exp_display = f"{exp_yyyymmdd[:4]}-{exp_yyyymmdd[4:6]}-{exp_yyyymmdd[6:8]}"

    _log("[THETA] ThetaData capability explorer (Phase 2 / 2.5)", json_mode)
    _log("[THETA] Base URL: " + BASE_URL, json_mode)
    _log("", json_mode)

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
                        _log_stderr(f"[THETA] symbol={symbol} price=(skip)", json_mode)
                        continue
                except httpx.RequestError as e:
                    _log_stderr(f"[THETA] symbol={symbol} request failed: {e}", json_mode)
                    continue
                rows = _parse_csv(text)
                if not rows:
                    _log(f"[THETA] symbol={symbol} price=(no rows)", json_mode)
                    continue
                header, data_start = _header_or_default(rows, ["ms_of_day", "price", "date"])
                for row in rows[data_start:]:
                    if not row:
                        continue
                    _log_schema_mismatch(row, header, "stock", json_mode)
                    if stock_quote_ts is None:
                        stock_quote_ts = _parse_utc_from_row(row, header)
                        if verbose and not json_mode:
                            print(f"[THETA] stock timestamp: {stock_quote_ts} (age_sec={_age_seconds(stock_quote_ts, now_utc)})", file=sys.stderr)
                        if stock_quote_ts is None:
                            _log_stderr("[THETA] timestamp missing for stock quote", json_mode)
                    pcl = _pick(row, header, "price", "close", "last")
                    price = pcl[0] or pcl[1] or pcl[2]
                    if price is None and len(row) >= 2:
                        try:
                            price = float(row[1])
                        except (ValueError, TypeError):
                            pass
                    if price is not None:
                        cap["stocks"] = "OK"
                        _log(f"[THETA] symbol={symbol} price={price:.2f}", json_mode)
                    else:
                        _log(f"[THETA] symbol={symbol} price=(missing)", json_mode)
                    break
            _log("", json_mode)

            # --- (b) Option snapshot OHLC ---
            ohlc_ok = False
            vol_from_ohlc: Any = None
            for path in ["/option/snapshot/ohlc", "/option/bulk_snapshot/ohlc", "/bulk_snapshot/option/ohlc"]:
                try:
                    params: dict[str, Any] = {"symbol": OPTION_ROOT, "exp": exp_yyyymmdd, "right": OPTION_RIGHT, "strike": OPTION_STRIKE_1_10_CENT}
                    if "bulk" in path:
                        params = {"symbol": OPTION_ROOT, "exp": exp_yyyymmdd}
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
                    if option_ohlc_ts is None:
                        option_ohlc_ts = _parse_utc_from_row(row, header)
                        if verbose and not json_mode:
                            print(f"[THETA] option_ohlc timestamp: {option_ohlc_ts} (age_sec={_age_seconds(option_ohlc_ts, now_utc)})", file=sys.stderr)
                        if option_ohlc_ts is None:
                            _log_stderr("[THETA] timestamp missing for option OHLC", json_mode)
                    close_val = _pick(row, header, "close")[0]
                    vol_val = _pick(row, header, "volume")[0]
                    if close_val is not None:
                        ohlc_ok = True
                        cap["options_ohlc"] = "OK"
                        vol_from_ohlc = vol_val
                    strike_display = OPTION_STRIKE_1_10_CENT / 1000.0
                    _log(f"[THETA] option={OPTION_ROOT} {exp_display} {OPTION_RIGHT} {strike_display:.0f} close={close_val} volume={vol_from_ohlc}", json_mode)
                    break
                if ohlc_ok:
                    break
            if not ohlc_ok:
                _log(f"[THETA] option={OPTION_ROOT} (no option OHLC data)", json_mode)
            _log("", json_mode)

            # --- (c) Option Greeks (delta, theta, vega, iv) ---
            greeks_ok = False
            iv_ok = False
            for path in ["/bulk_snapshot/option/greeks", "/option/bulk_snapshot/greeks"]:
                try:
                    text = _req_csv(client, path, {"symbol": OPTION_ROOT, "exp": exp_yyyymmdd})
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
                    _log_schema_mismatch(row, header, "greeks", json_mode)
                    if greeks_ts is None:
                        greeks_ts = _parse_utc_from_row(row, header)
                        if verbose and not json_mode:
                            print(f"[THETA] greeks timestamp: {greeks_ts} (age_sec={_age_seconds(greeks_ts, now_utc)})", file=sys.stderr)
                        if greeks_ts is None:
                            _log_stderr("[THETA] timestamp missing for greeks", json_mode)
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
                    _log(f"[THETA] option={OPTION_ROOT} {exp_display} {OPTION_RIGHT} {OPTION_STRIKE_1_10_CENT/1000:.0f} delta={delta} iv={iv}", json_mode)
                    break
                if greeks_ok or iv_ok:
                    break
            if not greeks_ok and not iv_ok:
                _log(f"[THETA] option={OPTION_ROOT} (no greeks/iv data)", json_mode)
            _log("", json_mode)

            # --- (d) Volume (from OHLC) and Open Interest ---
            if vol_from_ohlc is not None:
                _log(f"[THETA] volume from OHLC: {vol_from_ohlc}", json_mode)
            # OI: try common column names in options/greeks responses
            for path in ["/bulk_snapshot/option/greeks", "/option/bulk_snapshot/ohlc"]:
                try:
                    text = _req_csv(client, path, {"symbol": OPTION_ROOT, "exp": exp_yyyymmdd})
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
                _log("[THETA] oi: not found in sampled endpoints", json_mode)
            _log("", json_mode)

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
            _log(f"[THETA] index_support: {' '.join(parts)}", json_mode)
            _log("", json_mode)

            # --- Phase 2.5: freshness, per-capability health, overall health, contract ---
            stock_age = _age_seconds(stock_quote_ts, now_utc)
            option_ts = greeks_ts if greeks_ts is not None else option_ohlc_ts
            option_age = _age_seconds(option_ts, now_utc)
            freshness = {
                "stock_quote_age_sec": stock_age,
                "option_data_age_sec": option_age,
            }

            def _cap_health(data_ok: bool, age_sec: Optional[int], max_age: int) -> str:
                if not data_ok:
                    return "FAIL"
                if age_sec is None:
                    return "WARN"  # UNKNOWN never PASS
                if age_sec <= max_age:
                    return "PASS"
                return "WARN"

            option_ohlc_age = _age_seconds(option_ohlc_ts, now_utc) if option_ohlc_ts is not None else None
            cap_health = {
                "stocks": _cap_health(cap["stocks"] == "OK", stock_age, STOCK_QUOTE_MAX_AGE_SECONDS),
                "options_ohlc": _cap_health(cap["options_ohlc"] == "OK", option_ohlc_age, OPTION_DATA_MAX_AGE_SECONDS),
                "greeks": _cap_health(cap["greeks"] == "OK", _age_seconds(greeks_ts, now_utc) if greeks_ts is not None else option_age, OPTION_DATA_MAX_AGE_SECONDS),
                "iv": _cap_health(cap["iv"] == "OK", _age_seconds(greeks_ts, now_utc) if greeks_ts is not None else option_age, OPTION_DATA_MAX_AGE_SECONDS),
                "oi": _cap_health(cap["oi"] == "OK", option_age, OPTION_DATA_MAX_AGE_SECONDS),
            }

            notes: list[str] = []
            if stock_quote_ts is None and cap["stocks"] == "OK":
                notes.append("timestamp missing for stock quote")
            if option_ohlc_ts is None and cap["options_ohlc"] == "OK":
                notes.append("timestamp missing for option OHLC")
            if greeks_ts is None and (cap["greeks"] == "OK" or cap["iv"] == "OK"):
                notes.append("timestamp missing for greeks")
            if option_age is not None and option_age > OPTION_DATA_MAX_AGE_SECONDS and (cap["options_ohlc"] == "OK" or cap["greeks"] == "OK"):
                notes.append("option data stale")
            if stock_age is not None and stock_age > STOCK_QUOTE_MAX_AGE_SECONDS and cap["stocks"] == "OK":
                notes.append("stock quote stale")
            if index_support.get("SPX") == "NO":
                notes.append("SPX unsupported")

            if cap_health["stocks"] == "FAIL":
                overall = "FAIL"
            elif any(cap_health[k] in ("WARN", "FAIL") for k in ("options_ohlc", "greeks", "iv", "oi")):
                overall = "WARN"
            else:
                overall = "PASS"

            contract = {
                "source": "REALTIME",
                "timestamp": now_utc.isoformat(),
                "health": overall,
                "freshness": dict(freshness),
                "capabilities": dict(cap_health),
                "notes": list(notes),
            }

            _log("[THETA] capabilities summary:", json_mode)
            _log(f"  - stocks: {cap['stocks']} -> {cap_health['stocks']}", json_mode)
            _log(f"  - options_ohlc: {cap['options_ohlc']} -> {cap_health['options_ohlc']}", json_mode)
            _log(f"  - greeks: {cap['greeks']} -> {cap_health['greeks']}", json_mode)
            _log(f"  - iv: {cap['iv']} -> {cap_health['iv']}", json_mode)
            _log(f"  - oi: {cap['oi']} -> {cap_health['oi']}", json_mode)
            _log(f"[THETA] overall health: {overall}", json_mode)
            _log("", json_mode)
            _log("[THETA] capability explorer done", json_mode)

            exit_code = 1 if overall == "FAIL" else 0
            return (contract, exit_code)

    except httpx.ConnectError as e:
        print("[THETA] ERROR: Theta Terminal is not running or not reachable.", file=sys.stderr)
        print("[THETA] Start ThetaTerminal v3 on port 25503 (see docs/RUNBOOK_EXECUTION.md).", file=sys.stderr)
        print(f"[THETA] Detail: {e}", file=sys.stderr)
        return ({}, 1)
    except Exception as e:
        print(f"[THETA] ERROR: {e}", file=sys.stderr)
        return ({}, 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ThetaData capability explorer (Phase 2/2.5)")
    ap.add_argument("--verbose", action="store_true", help="Show timestamps and age calculations")
    ap.add_argument("--json", action="store_true", dest="json_mode", help="Print only the final contract as JSON")
    args = ap.parse_args()
    contract, code = run(verbose=args.verbose, json_mode=args.json_mode)
    if args.json_mode and contract:
        print(json.dumps(contract, default=str))
    sys.exit(code)
