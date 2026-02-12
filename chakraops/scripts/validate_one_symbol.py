#!/usr/bin/env python3
"""
Single-ticker runtime validation: proves we fetch required fields from ORATS and wire
the same snapshot through all endpoints. Calls API (server must already be running).
Writes JSON artifacts and a human-readable markdown analysis. No cached DB reads.

Usage:
  python scripts/validate_one_symbol.py [--symbol SPY] [--base http://127.0.0.1:8000]

Requires: Server running (e.g. uvicorn app.api.server:app --port 8000). Does NOT auto-start.

Exit codes:
  0 - All required fields present, Stage-1 would PASS (not stale); eligibility/contract checks OK.
  1 - Request/IO error (e.g. connection refused, non-200).
  2 - One or more required fields missing/null (see docs/VALIDATE_ONE_SYMBOL_EXPECTATIONS.md).
  3 - Stage-1 verdict would be BLOCKED (e.g. stale quote_date).
  4 - Contract missing fields (contract_data.available but required chain fields missing).
  5 - Contract unavailable but expected (symbol_eligibility PASS but contract_data not available).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore


BASE_DEFAULT = "http://127.0.0.1:8000"
SYMBOL_DEFAULT = "SPY"

# Required Stage-1 fields (must match data_requirements.REQUIRED_STAGE1_FIELDS)
REQUIRED_FIELDS = ("price", "bid", "ask", "volume", "quote_date", "iv_rank")
# Snapshot keys: API may expose quote_as_of for display; quote_date is the canonical date
QUOTE_DATE_KEYS = ("quote_date", "quote_as_of")


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


def _get_universe_with_retry(url: str, timeout: int = 10, retry_sleep: float = 1.0) -> tuple[dict | None, int, str]:
    """GET universe URL with 10s timeout; retry once after 1s on failure (resilience, not fallback)."""
    data, code, err = _get(url, timeout=timeout)
    if code == 200 and data is not None:
        return data, code, err
    time.sleep(retry_sleep)
    return _get(url, timeout=timeout)


def _trading_days_since(as_of_date: date | None) -> int | None:
    """Use app's market calendar so staleness matches Stage-1 exactly."""
    if as_of_date is None:
        return None
    try:
        from app.core.environment.market_calendar import trading_days_since as _tds
        return _tds(as_of_date)
    except Exception:
        # Fallback: calendar days (no holiday awareness)
        today = date.today()
        if as_of_date > today:
            return None
        return max(0, (today - as_of_date).days)


def _parse_quote_date(snapshot: dict) -> date | None:
    """Parse quote date from snapshot dict (quote_date or quote_as_of, YYYY-MM-DD)."""
    raw = snapshot.get("quote_date") or snapshot.get("quote_as_of")
    if not raw:
        return None
    s = str(raw).strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None


def _contract_assert(snapshot: dict, missing_reasons: dict, stale_threshold_days: int = 1) -> tuple[list[str], list[str], bool]:
    """
    Returns (missing_fields, block_reasons, is_stale).
    missing_fields: required fields that are null or in missing_reasons.
    block_reasons: human-readable reasons (missing field or stale).
    is_stale: True if quote_date is older than stale_threshold_days.
    """
    missing_fields: list[str] = []
    block_reasons: list[str] = []

    for f in REQUIRED_FIELDS:
        val = snapshot.get(f)
        if f == "quote_date":
            val = val or snapshot.get("quote_as_of")
        # volume=0 is valid; only None/missing counts as missing
        if val is None:
            missing_fields.append(f)
            reason = missing_reasons.get(f) or "not provided"
            block_reasons.append(f"missing: {f} ({reason})")

    quote_parsed = _parse_quote_date(snapshot)
    days_since = _trading_days_since(quote_parsed) if quote_parsed else None
    is_stale = days_since is not None and days_since > stale_threshold_days
    if is_stale and "quote_date" not in missing_fields:
        block_reasons.append(f"DATA_STALE: quote_date is {days_since} day(s) old (threshold {stale_threshold_days})")

    return missing_fields, block_reasons, is_stale


# Required chain fields when contract_data.available (Phase 3.3.1)
REQUIRED_CONTRACT_DATA_KEYS = ("expiration_count", "contract_count", "required_fields_present")


def _eligibility_and_contract_assert(diagnostics: dict) -> tuple[int | None, list[str]]:
    """
    Validate symbol_eligibility, contract_data, contract_eligibility present and,
    when contract_data.available, required chain fields exist.
    Returns (exit_code or None, list of error messages).
    None = no exit; 4 = contract missing fields; 5 = contract unavailable but expected.
    """
    errs: list[str] = []
    if not isinstance(diagnostics, dict):
        return 2, ["diagnostics response is not a dict"]

    # 1) symbol_eligibility present
    se = diagnostics.get("symbol_eligibility")
    if se is None:
        errs.append("symbol_eligibility missing")
    elif not isinstance(se, dict):
        errs.append("symbol_eligibility is not a dict")

    # 2) contract_data present
    cd = diagnostics.get("contract_data")
    if cd is None:
        errs.append("contract_data missing")
    elif not isinstance(cd, dict):
        errs.append("contract_data is not a dict")

    # 3) contract_eligibility present
    ce = diagnostics.get("contract_eligibility")
    if ce is None:
        errs.append("contract_eligibility missing")
    elif not isinstance(ce, dict):
        errs.append("contract_eligibility is not a dict")

    if errs:
        return 2, errs  # required structure missing (symbol_eligibility / contract_data / contract_eligibility)

    # 4) If contract_data.available: check schema. Do NOT treat required_fields_present==False
    #    as hard failure when chain exists - log as WARN and exit 0 (selection may have failed for other reasons).
    available = cd.get("available") is True
    if available:
        for key in REQUIRED_CONTRACT_DATA_KEYS:
            if key not in cd:
                errs.append(f"contract_data.available but missing key: {key}")
        if errs:
            return 4, errs
        # required_fields_present==False: log but do not fail (exit 0) - chain exists, may be selection failure
        if cd.get("required_fields_present") is False:
            return None, ["WARN: contract_data.required_fields_present is False (chain has puts but none with all required fields) - check puts_with_required_fields"]

    # 5) Exit 5 ONLY when chain truly unavailable: Stage-1 PASS but Stage-2 did not run or returned no contracts.
    #    Do NOT exit 5 when contract_data.available=True and contract_eligibility.status=FAIL — that's normal
    #    (chain fetched, but no contract passed filters).
    se_status = (se or {}).get("status") if isinstance(se, dict) else None
    ce_status = (ce or {}).get("status") if isinstance(ce, dict) else None
    if se_status == "PASS" and not available:
        return 5, ["EXIT 5: Stage-1 PASS but chain truly unavailable (contract_data.available=False)"]
    # Log info when chain available but no contract passed (not an error)
    if se_status == "PASS" and available and ce_status == "FAIL":
        return None, []  # INFO handled by caller if desired; no exit

    return None, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one symbol: call API, save artifacts, run contract assertion. Server must be running."
    )
    parser.add_argument("--symbol", default=SYMBOL_DEFAULT, help=f"Ticker (default: {SYMBOL_DEFAULT})")
    parser.add_argument("--base", default=BASE_DEFAULT, help=f"API base URL (default: {BASE_DEFAULT})")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    symbol = (args.symbol or SYMBOL_DEFAULT).strip().upper()

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
        with open(out_snap, "w", encoding="utf-8") as f:
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
        with open(out_diag, "w", encoding="utf-8") as f:
            json.dump(data_diag, f, indent=2)
        print(f"Wrote {out_diag}")
        # Stage-2 trace for harness comparison (Phase 3.0); always write file
        trace = data_diag.get("stage2_trace")
        out_trace = out_dir / f"{symbol}_stage2_trace.json"
        if isinstance(trace, dict):
            with open(out_trace, "w", encoding="utf-8") as f:
                json.dump(trace, f, indent=2, default=str)
        else:
            with open(out_trace, "w", encoding="utf-8") as f:
                json.dump({"symbol": symbol, "stage2_trace": None, "message": "Trace not available (LIVE mode or pipeline did not return trace)."}, f, indent=2)
        print(f"Wrote {out_trace}")
    else:
        print(f"symbol-diagnostics failed: {err_diag}", file=sys.stderr)

    # 3) GET /api/view/universe (10s timeout, retry once after 1s)
    url_universe = f"{base}/api/view/universe"
    data_univ, code_univ, err_univ = _get_universe_with_retry(url_universe)
    out_univ = out_dir / "universe.json"
    if data_univ is not None:
        with open(out_univ, "w", encoding="utf-8") as f:
            json.dump(data_univ, f, indent=2)
        print(f"Wrote {out_univ}")
    else:
        with open(out_univ, "w", encoding="utf-8") as f:
            json.dump({"error": err_univ or str(code_univ), "symbols": [], "updated_at": None}, f, indent=2)
        print(f"Wrote {out_univ} (universe returned non-200 or invalid JSON)")
    if code_univ != 200:
        errors.append(f"universe: {code_univ} {err_univ or 'non-200'}")

    # --- Snapshot for contract checks ---
    snap_obj = (data_snap or {}).get("snapshot")
    if not isinstance(snap_obj, dict):
        snap_obj = (data_diag or {}).get("stock") if data_diag else {}
    if not isinstance(snap_obj, dict):
        snap_obj = {}
    missing_reasons = (data_snap or {}).get("missing_reasons") or (snap_obj.get("missing_reasons") or {})
    missing_reasons = missing_reasons if isinstance(missing_reasons, dict) else {}

    try:
        from app.core.data.data_requirements import STAGE1_STALE_TRADING_DAYS
        stale_threshold = STAGE1_STALE_TRADING_DAYS
    except Exception:
        stale_threshold = 1
    missing_fields, block_reasons, is_stale = _contract_assert(snap_obj, missing_reasons, stale_threshold_days=stale_threshold)

    # --- Markdown analysis ---
    analysis_lines = [
        f"# Validation: {symbol}",
        "",
        "## Endpoints",
        f"- `GET {url_snapshot}` → {out_snap.name}",
        f"- `GET {url_diag}` → {out_diag.name}",
        f"- `GET {url_universe}` → {out_univ.name}",
        "",
        "## Required fields (Stage-1)",
        f"Expected: {', '.join(REQUIRED_FIELDS)}.",
        "",
    ]
    for f in REQUIRED_FIELDS:
        key = f if f != "quote_date" else ("quote_date / quote_as_of")
        val = snap_obj.get(f) if f != "quote_date" else (snap_obj.get("quote_date") or snap_obj.get("quote_as_of"))
        status = "MISSING" if f in missing_fields else "present"
        analysis_lines.append(f"- **{key}**: {val!r} ({status})")
    analysis_lines.append("")
    analysis_lines.append("## missing_reasons (required fields)")
    if not missing_reasons:
        analysis_lines.append("(empty — expected when ORATS returns all required data)")
    else:
        for k in REQUIRED_FIELDS:
            analysis_lines.append(f"- **{k}**: " + (missing_reasons.get(k) or "—"))
    analysis_lines.append("")
    # Stage-2 /strikes/options telemetry (endpoint and non-null counts)
    cd = (data_diag or {}).get("contract_data") or {}
    opt = (data_diag or {}).get("options") or {}
    tel = cd.get("strikes_options_telemetry") or opt.get("strikes_options_telemetry")
    if tel and isinstance(tel, dict):
        analysis_lines.append("## /strikes/options telemetry")
        analysis_lines.append(f"- **endpoint_used**: {tel.get('endpoint_used', '—')}")
        analysis_lines.append(f"- **requested_tickers_count**: {tel.get('requested_tickers_count', '—')}")
        analysis_lines.append(f"- **response_rows**: {tel.get('response_rows', '—')}")
        analysis_lines.append(f"- **non_null_bidask**: {tel.get('non_null_bidask', '—')}")
        analysis_lines.append(f"- **non_null_oi**: {tel.get('non_null_oi', '—')}")
        analysis_lines.append(f"- **non_null_vol**: {tel.get('non_null_vol', '—')}")
        analysis_lines.append("")
    analysis_lines.append("## Stage-1 verdict")
    if missing_fields:
        analysis_lines.append("**BLOCK** — required field(s) missing: " + ", ".join(missing_fields))
        for r in block_reasons:
            analysis_lines.append(f"- {r}")
    elif is_stale:
        analysis_lines.append("**BLOCK** — quote_date stale")
        for r in block_reasons:
            analysis_lines.append(f"- {r}")
    else:
        analysis_lines.append("**PASS** — all required fields present and quote_date fresh.")
    analysis_lines.append("")

    out_md = out_dir / f"{symbol}_analysis.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(analysis_lines))
    print(f"Wrote {out_md}")

    # --- Console summary ---
    print("\n--- Summary ---")
    snapshot_time = (data_snap or {}).get("snapshot_time") or (data_diag or {}).get("fetched_at") or "N/A"
    print(f"snapshot_time: {snapshot_time}")
    if snap_obj:
        print(f"price: {snap_obj.get('price')}")
        print(f"bid: {snap_obj.get('bid')}")
        print(f"ask: {snap_obj.get('ask')}")
        print(f"volume: {snap_obj.get('volume')}")
        print(f"quote_as_of / quote_date: {snap_obj.get('quote_as_of') or snap_obj.get('quote_date')}")
        print(f"iv_rank: {snap_obj.get('iv_rank')}")
    print(f"missing_reasons (required keys): {[k for k in REQUIRED_FIELDS if (missing_reasons or {}).get(k)] or []}")
    if missing_fields:
        print(f"BLOCK reason: required field(s) missing: {missing_fields}", file=sys.stderr)
    if is_stale and not missing_fields:
        print("BLOCK reason: quote_date stale (Stage-1)", file=sys.stderr)
    for r in block_reasons:
        print(f"  {r}", file=sys.stderr)

    # --- Exit code: request errors first ---
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    # Required field missing => exit 2
    if missing_fields:
        return 2
    # Stage-1 BLOCKED (e.g. stale) => exit 3
    if is_stale:
        return 3
    # Phase 3.3.1: eligibility and contract checks (symbol_eligibility, contract_data, contract_eligibility)
    if data_diag is not None:
        exit_ec, msg_list = _eligibility_and_contract_assert(data_diag)
        if exit_ec is not None:
            for m in msg_list:
                print(m, file=sys.stderr)
            return exit_ec
        for m in msg_list:
            print(m, file=sys.stderr)  # WARN messages (e.g. required_fields_present False)
        # When chain available but no contract passed (FAIL), that's informational, not an error
        cd = data_diag.get("contract_data") or {}
        ce = data_diag.get("contract_eligibility") or {}
        if cd.get("available") is True and (ce or {}).get("status") == "FAIL":
            print("INFO: Chain available but no contracts passed filters.")
            print(f"  Reasons: {ce.get('reasons', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
