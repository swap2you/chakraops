#!/usr/bin/env python3
"""
Single-ticker validation: call API (server must already be running at http://127.0.0.1:8000),
save real JSON to artifacts/validate/, and print a compact summary.

Usage:
  python scripts/validate_one_symbol.py [--symbol AMD] [--base http://127.0.0.1:8000]

Requires: Server running (e.g. uvicorn app.api.server:app --port 8000). Does NOT auto-start.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore


BASE_DEFAULT = "http://127.0.0.1:8000"
SYMBOL_DEFAULT = "AMD"


def _get(url: str, timeout: int = 30) -> tuple[dict | None, int, str]:
    """GET url; return (parsed JSON or None, status_code, error_or_empty)."""
    if urllib is None:
        return None, 0, "urllib not available"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            data = json.loads(body)
            return data, resp.status, ""
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            data = json.loads(body)
        except Exception:
            data = None
        return data, e.code, str(e)
    except urllib.error.URLError as e:
        return None, 0, str(e.reason) if getattr(e, "reason", None) else str(e)
    except json.JSONDecodeError as e:
        return None, 0, f"JSON decode: {e}"
    except Exception as e:
        return None, 0, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one symbol: call API, save artifacts, print summary. Server must be running."
    )
    parser.add_argument("--symbol", default=SYMBOL_DEFAULT, help="Ticker (default: AMD)")
    parser.add_argument("--base", default=BASE_DEFAULT, help=f"API base URL (default: {BASE_DEFAULT})")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    symbol = (args.symbol or SYMBOL_DEFAULT).strip().upper()

    # Repo root: script in scripts/ -> parent is chakraops
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "artifacts" / "validate"
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # 1) GET /api/ops/snapshot?symbol=...
    url_snapshot = f"{base}/api/ops/snapshot?symbol={symbol}"
    data_snap, code_snap, err_snap = _get(url_snapshot)
    if code_snap != 200:
        errors.append(f"ops/snapshot: {code_snap} {err_snap or 'non-200'}")
    out_snap = out_dir / f"{symbol}_ops_snapshot.json"
    if data_snap is not None:
        with open(out_snap, "w") as f:
            json.dump(data_snap, f, indent=2)
        print(f"Wrote {out_snap}")
    else:
        print(f"ops/snapshot failed: {err_snap}", file=sys.stderr)

    # 2) GET /api/view/symbol-diagnostics?symbol=...
    url_diag = f"{base}/api/view/symbol-diagnostics?symbol={symbol}"
    data_diag, code_diag, err_diag = _get(url_diag)
    if code_diag != 200:
        errors.append(f"symbol-diagnostics: {code_diag} {err_diag or 'non-200'}")
    out_diag = out_dir / f"{symbol}_symbol_diagnostics.json"
    if data_diag is not None:
        with open(out_diag, "w") as f:
            json.dump(data_diag, f, indent=2)
        print(f"Wrote {out_diag}")
    else:
        print(f"symbol-diagnostics failed: {err_diag}", file=sys.stderr)

    # 3) Optional: GET /api/view/universe
    url_universe = f"{base}/api/view/universe"
    data_univ, code_univ, err_univ = _get(url_universe)
    out_univ = out_dir / "universe.json"
    if code_univ == 200 and data_univ is not None:
        with open(out_univ, "w") as f:
            json.dump(data_univ, f, indent=2)
        print(f"Wrote {out_univ}")
    else:
        if code_univ != 200:
            print(f"universe: {code_univ} (optional, skipped)", file=sys.stderr)

    # Compact summary from ops/snapshot or symbol-diagnostics
    print("\n--- Summary ---")
    snapshot_time = (data_snap or {}).get("snapshot_time") or (data_diag or {}).get("fetched_at") or "N/A"
    snap_obj = (data_snap or {}).get("snapshot")
    stock_obj = (data_diag or {}).get("stock") if data_diag else None
    stock = snap_obj if isinstance(snap_obj, dict) else (stock_obj if isinstance(stock_obj, dict) else {})
    missing = (data_snap or {}).get("missing_reasons") or (stock.get("missing_reasons") if isinstance(stock, dict) else {}) or {}
    fs = (data_snap or {}).get("field_sources") or (stock.get("field_sources") if isinstance(stock, dict) else {}) or {}
    print(f"snapshot_time: {snapshot_time}")
    if stock:
        print(f"stock.price: {stock.get('price')}")
        print(f"stock.bid: {stock.get('bid')}")
        print(f"stock.ask: {stock.get('ask')}")
        print(f"stock.volume: {stock.get('volume')}")
        print(f"quote_as_of: {stock.get('quote_as_of')}")
        print(f"iv_rank: {stock.get('iv_rank')}")
    print(f"missing_reasons keys: {list(missing.keys()) if missing else []}")
    print(f"field_sources keys: {list(fs.keys()) if fs else []}")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
