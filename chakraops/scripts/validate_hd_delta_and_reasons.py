#!/usr/bin/env python3
"""
Integration-ish validation: recompute HD, fetch symbol-diagnostics, print what the UI should display.
Useful to verify delta rejection sample wiring and reasons_explained.

Usage:
  python scripts/validate_hd_delta_and_reasons.py [--symbol HD] [--base http://127.0.0.1:8000]

Requires: Server running (e.g. uvicorn app.api.server:app --port 8000).
Pass x-ui-key if UI_API_KEY is set.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore

BASE_DEFAULT = "http://127.0.0.1:8000"
SYMBOL_DEFAULT = "HD"


def _headers() -> dict:
    """Include x-ui-key if UI_API_KEY is set."""
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    key = (os.getenv("UI_API_KEY") or "").strip()
    if key:
        h["x-ui-key"] = key
    return h


def _get(url: str, timeout: int = 60) -> tuple[dict | None, int, str]:
    if urllib is None:
        return None, 0, "urllib not available"
    try:
        req = urllib.request.Request(url, headers=_headers(), method="GET")
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


def _post(url: str, body: dict | None = None, timeout: int = 120) -> tuple[dict | None, int, str]:
    if urllib is None:
        return None, 0, "urllib not available"
    try:
        data_bytes = json.dumps(body or {}).encode() if body else b""
        req = urllib.request.Request(url, data=data_bytes, headers=_headers(), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = resp.read().decode()
            parsed = json.loads(out)
            return parsed, resp.status, ""
    except urllib.error.HTTPError as e:
        try:
            body_read = e.read().decode()
            parsed = json.loads(body_read)
        except Exception:
            parsed = None
        return parsed, e.code, str(e)
    except urllib.error.URLError as e:
        return None, 0, str(e.reason) if getattr(e, "reason", None) else str(e)
    except json.JSONDecodeError as e:
        return None, 0, f"JSON decode: {e}"
    except Exception as e:
        return None, 0, str(e)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Recompute symbol, fetch diagnostics, print UI-relevant fields.")
    parser.add_argument("--symbol", default=SYMBOL_DEFAULT, help=f"Ticker (default: {SYMBOL_DEFAULT})")
    parser.add_argument("--base", default=BASE_DEFAULT, help=f"API base URL (default: {BASE_DEFAULT})")
    parser.add_argument("--force", action="store_true", help="Override market-closed guardrail for recompute")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    symbol = (args.symbol or SYMBOL_DEFAULT).strip().upper()

    print(f"POST {base}/api/ui/symbols/{symbol}/recompute" + ("?force=true" if args.force else ""))
    url_recompute = f"{base}/api/ui/symbols/{symbol}/recompute" + ("?force=true" if args.force else "")
    rec, code_rec, err_rec = _post(url_recompute, timeout=120)
    if code_rec != 200:
        print(f"Recompute failed: {code_rec} {err_rec}", file=sys.stderr)
        if code_rec == 0:
            print("  (Server must be running: uvicorn app.api.server:app --port 8000)", file=sys.stderr)
        elif rec and isinstance(rec, dict) and "detail" in rec:
            print(f"  detail: {rec['detail']}", file=sys.stderr)
        return 1
    print("Recompute OK")

    print(f"\nGET {base}/api/ui/symbol-diagnostics?symbol={symbol}")
    url_diag = f"{base}/api/ui/symbol-diagnostics?symbol={symbol}"
    diag, code_diag, err_diag = _get(url_diag, timeout=30)
    if code_diag != 200:
        print(f"Diagnostics failed: {code_diag} {err_diag}", file=sys.stderr)
        return 1

    print("\n--- Fields the UI displays ---")
    stage2 = diag.get("stage2_status") or diag.get("stage_status") or "—"
    primary = diag.get("primary_reason") or "—"
    print(f"stage2_status: {stage2}")
    print(f"primary_reason: {primary}")

    reasons = diag.get("reasons_explained") or []
    if reasons:
        print(f"\nreasons_explained ({len(reasons)}):")
        for i, r in enumerate(reasons):
            msg = (r.get("message") or "")[:200]
            print(f"  [{i}] {msg}")
    else:
        print("\nreasons_explained: (empty or missing)")

    sample = diag.get("sample_rejected_due_to_delta") or []
    if sample:
        print(f"\ntrace.sample_rejected_due_to_delta ({len(sample)}):")
        for i, s in enumerate(sample[:3]):
            obs_abs = s.get("observed_delta_decimal_abs")
            obs_pct = s.get("observed_delta_pct_abs")
            target = s.get("target_range_decimal", "—")
            print(f"  [{i}] observed_delta_decimal_abs={obs_abs} observed_delta_pct_abs={obs_pct} target_range={target}")
    else:
        print("\ntrace.sample_rejected_due_to_delta: (empty or missing)")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
