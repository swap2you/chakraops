#!/usr/bin/env python3
"""
ThetaData real-time probe utility.

This is an isolated probe script used to validate ThetaData REST API access
before pipeline integration. It fetches snapshot OHLC from the option endpoint,
parses CSV, and prints human-readable lines. No DB writes, no heartbeat/snapshot
imports, no dashboard changes.

Phase 1 of real-time data integration (learning + validation only).
"""

import csv
import io
import sys
from typing import Any

import httpx

# --- Config (no app imports) ---
BASE_URL = "http://127.0.0.1:25503/v3"
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
TIMEOUT = 15.0

# Optional: symbol -> strike in 1/10 cent for single-contract probe
STRIKE_1_10_CENT = {
    "SPY": 50000,
    "QQQ": 50000,
    "AAPL": 20000,
    "MSFT": 45000,
}


def _req(
    client: httpx.Client,
    path: str,
    params: dict[str, Any],
    accept_csv: bool = True,
) -> str:
    """GET and return response text. Caller handles errors."""
    p = dict(params)
    if accept_csv:
        p["format"] = "csv"
        p["use_csv"] = "true"  # ThetaData docs use use_csv for CSV output
    r = client.get(path, params=p, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def _parse_csv(text: str) -> list[list[str]]:
    """Parse CSV text into rows. Does not crash on bad rows."""
    rows: list[list[str]] = []
    try:
        reader = csv.reader(io.StringIO(text))
        for raw in reader:
            rows.append(raw)
    except csv.Error as e:
        print(f"[THETA] csv parse error: {e}", file=sys.stderr)
    return rows


def _pick(row: list[str], header: list[str], *names: str) -> tuple[Any, ...]:
    """Return (value, ...) for first matching column name. Missing -> None."""
    out: list[Any] = []
    for name in names:
        name_lower = name.lower()
        idx = next((i for i, h in enumerate(header) if (h or "").strip().lower() == name_lower), -1)
        if idx >= 0 and idx < len(row):
            try:
                v = row[idx].strip()
                if name_lower in ("open", "high", "low", "close", "volume", "count"):
                    out.append(float(v) if v else None)
                else:
                    out.append(v if v else None)
            except (ValueError, TypeError):
                out.append(None)
        else:
            out.append(None)
    return tuple(out)


def _format_ts(ms_of_day: Any, date_val: Any) -> str:
    """Format timestamp from ms_of_day and/or date."""
    if date_val is not None and str(date_val).strip():
        return str(date_val).strip()
    if ms_of_day is not None:
        return str(ms_of_day)
    return ""


def run_probe() -> int:
    """Run ThetaData probe. Returns 0 on success, 1 on terminal down / fatal error."""
    print("[THETA] ThetaData real-time probe (option snapshot OHLC)")
    print("[THETA] Base URL:", BASE_URL)
    print("[THETA] Symbols:", ", ".join(SYMBOLS))
    print()

    try:
        with httpx.Client(base_url=BASE_URL) as client:
            for symbol in SYMBOLS:
                # Try /option/snapshot/ohlc with expiration="*" per user spec
                path = "/option/snapshot/ohlc"
                params = {
                    "symbol": symbol,
                    "exp": "*",
                    "right": "C",
                    "strike": STRIKE_1_10_CENT.get(symbol, 50000),
                }
                text = None
                try:
                    text = _req(client, path, params)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        path = "/option/bulk_snapshot/ohlc"
                        params_bulk = {"symbol": symbol, "exp": "0"}
                        try:
                            text = _req(client, path, params_bulk)
                        except httpx.HTTPStatusError:
                            path = "/bulk_snapshot/option/ohlc"
                            try:
                                text = _req(client, path, params_bulk)
                            except httpx.HTTPStatusError:
                                print(f"[THETA] symbol={symbol} 404 on snapshot paths; tried bulk_snapshot", file=sys.stderr)
                                continue
                    elif e.response.status_code == 400:
                        params["exp"] = "0"
                        try:
                            text = _req(client, path, params)
                        except httpx.HTTPStatusError:
                            print(f"[THETA] symbol={symbol} path={path} failed (exp=* and exp=0)", file=sys.stderr)
                            continue
                    else:
                        print(f"[THETA] symbol={symbol} HTTP {e.response.status_code} path={path}", file=sys.stderr)
                        continue
                except httpx.RequestError as e:
                    print(f"[THETA] symbol={symbol} request failed: {e}", file=sys.stderr)
                    continue
                if text is None:
                    continue

                rows = _parse_csv(text)
                if not rows:
                    print(f"[THETA] symbol={symbol} price=(no rows) volume=(none) timestamp=(none)")
                    continue

                # Log schema info on first symbol for learning
                if symbol == SYMBOLS[0]:
                    print(f"[THETA] schema sample: row_count={len(rows)} first_row_len={len(rows[0])} raw_first={rows[0][:8]}")
                    if len(rows[0]) != 8:
                        print(f"[THETA] schema note: expected 8 cols [ms_of_day,open,high,low,close,volume,count,date]; got {len(rows[0])}")

                header = [c.strip() for c in rows[0]]
                # Treat first row as header if it looks like column names
                data_start = 1 if any(h and not h.isdigit() for h in header) else 0
                if data_start == 0:
                    header = ["ms_of_day", "open", "high", "low", "close", "volume", "count", "date"][: len(rows[0])]

                for row in rows[data_start:]:
                    if not row:
                        continue
                    if len(row) != len(header):
                        print(f"[THETA] schema: row_len={len(row)} header_len={len(header)} raw_row={row[:10]}", file=sys.stderr)
                    pv = _pick(row, header, "close", "volume")
                    ts_vals = _pick(row, header, "ms_of_day", "date")
                    price, volume = pv[0], pv[1]
                    ts_ms, ts_date = ts_vals[0], ts_vals[1]
                    timestamp = _format_ts(ts_ms, ts_date)
                    # Log found vs missing
                    found = []
                    if price is not None:
                        found.append("price")
                    else:
                        found.append("price=MISSING")
                    if volume is not None:
                        found.append("volume")
                    else:
                        found.append("volume=MISSING")
                    if timestamp:
                        found.append("timestamp")
                    else:
                        found.append("timestamp=MISSING")
                    if symbol == SYMBOLS[0] and (price is None or volume is None or not timestamp):
                        print(f"[THETA] fields: {', '.join(found)}", file=sys.stderr)
                    p_str = f"price={price:.2f}" if price is not None else "price=(missing)"
                    v_str = f"volume={int(volume)}" if volume is not None else "volume=(missing)"
                    t_str = f"timestamp={timestamp}" if timestamp else "timestamp=(missing)"
                    print(f"[THETA] symbol={symbol} {p_str} {v_str} {t_str}")
                    break
            print()
            print("[THETA] probe done")
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
    sys.exit(run_probe())
