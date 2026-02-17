#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Market live validation: ONE PIPELINE / ONE ARTIFACT / ONE STORE (v2-only).

Runs evaluation, validates canonical store and (optionally) API invariants.
Produces: out/market_live_validation_report.md, out/TRUTH_TABLE_V2.md,
          out/decision_<ts>_canonical_copy.json

Exit: 0 pass, 2 validation fail, 3 runtime error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO / ".env")
except ImportError:
    pass

API_BASE = os.getenv("VALIDATION_API_BASE", "http://127.0.0.1:8000")
UI_KEY = (os.getenv("UI_API_KEY") or "").strip()

# Valid bands
BANDS = {"A", "B", "C", "D"}


def _get_store_path() -> Path:
    from app.core.eval.evaluation_store_v2 import get_decision_store_path
    return get_decision_store_path()


def _out_dir() -> Path:
    return _get_store_path().parent


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if UI_KEY:
        h["x-ui-key"] = UI_KEY
    return h


def _get(url: str) -> Tuple[int, Optional[Dict[str, Any]]]:
    import urllib.request
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:
        return -1, {"_error": str(e)}


def _post(url: str, data: Dict[str, Any]) -> Tuple[int, Optional[Dict[str, Any]]]:
    import urllib.request
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:
        return -1, {"_error": str(e)}


# ---------------------------------------------------------------------------
# A) Canonical store file invariants
# ---------------------------------------------------------------------------

def _validate_store_invariants(data: Dict[str, Any], failures: List[str], checks: List[Tuple[str, bool, str]]) -> None:
    """Validate (A): file exists, v2, pipeline_timestamp, data_source not mock, symbol rows, band_reason."""
    meta = data.get("metadata") or {}
    symbols = data.get("symbols") or []

    ver = meta.get("artifact_version")
    ok = ver == "v2"
    checks.append(("artifact_version == v2", ok, f"got {ver!r}"))
    if not ok:
        failures.append("artifact_version must be v2")

    ts = meta.get("pipeline_timestamp")
    ok_ts = bool(ts) and isinstance(ts, str)
    if ok_ts and ts:
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            ok_ts = False
    checks.append(("metadata.pipeline_timestamp present and ISO", ok_ts, f"got {ts!r}"[:80]))
    if not ok_ts:
        failures.append("metadata.pipeline_timestamp missing or not ISO")

    ds = (meta.get("data_source") or "").strip().lower()
    ok_ds = ds not in ("mock", "scenario")
    checks.append(("metadata.data_source not mock/scenario (LIVE)", ok_ds, f"data_source={ds!r}"))
    if not ok_ds:
        failures.append("data_source must not be mock/scenario for LIVE")

    bad_bands = []
    bad_reasons = []
    for row in symbols:
        sym = row.get("symbol", "?")
        band = (row.get("band") or "").strip().upper()
        band_ok = band in BANDS
        band_reason_ok = bool((row.get("band_reason") or "").strip())
        if not band_ok:
            bad_bands.append(sym)
            failures.append(f"Symbol {sym}: band must be in A|B|C|D, got {row.get('band')!r}")
        elif not band_reason_ok:
            bad_reasons.append(sym)
            failures.append(f"Symbol {sym}: band_reason must be non-empty")
        else:
            br = (row.get("band_reason") or "").lower()
            if f"band {band}" not in br and f"band {band.lower()}" not in br:
                failures.append(f"Symbol {sym}: band_reason must reference band {band}")

    checks.append(("All symbol rows: band in A/B/C/D", len(bad_bands) == 0, f"invalid: {bad_bands[:10]}" if bad_bands else "ok"))
    checks.append(("All symbol rows: band_reason non-empty", len(bad_reasons) == 0, f"missing: {bad_reasons[:10]}" if bad_reasons else "ok"))


def _run_evaluation(checks: List[Tuple[str, bool, str]], failures: List[str]) -> bool:
    """Run run_and_save.py --all --output-dir out. Return True if success."""
    try:
        result = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "run_and_save.py"), "--all", "--output-dir", "out"],
            cwd=str(_REPO),
            env={**os.environ, "PYTHONPATH": str(_REPO)},
            capture_output=True,
            text=True,
            timeout=600,
        )
        ok = result.returncode == 0
        checks.append(("run_and_save.py --all --output-dir out", ok, result.stderr or result.stdout or str(result)))
        if not ok:
            failures.append("run_and_save.py failed")
        return ok
    except subprocess.TimeoutExpired:
        checks.append(("run_and_save.py --all", False, "Timeout 600s"))
        failures.append("run_and_save timed out")
        return False
    except Exception as e:
        checks.append(("run_and_save.py --all", False, str(e)))
        failures.append(str(e))
        return False


def _read_store() -> Optional[Dict[str, Any]]:
    path = _get_store_path()
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_canonical_copy(data: Dict[str, Any]) -> Path:
    out = _out_dir()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    dest = out / f"decision_{ts}_canonical_copy.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return dest


def _generate_truth_table(data: Dict[str, Any], path: Path) -> None:
    """Write out/TRUTH_TABLE_V2.md with summary, per-symbol table, top blockers."""
    meta = data.get("metadata") or {}
    symbols = data.get("symbols") or []
    ts = meta.get("pipeline_timestamp", "")
    phase = meta.get("market_phase", "")
    universe_size = meta.get("universe_size", len(symbols))
    eval_s1 = meta.get("evaluated_count_stage1", "")
    eval_s2 = meta.get("evaluated_count_stage2", "")
    eligible = meta.get("eligible_count", "")

    lines = [
        "# TRUTH TABLE (v2 artifact)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"- **pipeline_timestamp**: {ts}",
        f"- **market_phase**: {phase}",
        f"- **universe_size**: {universe_size}",
        f"- **evaluated_count_stage1**: {eval_s1}",
        f"- **evaluated_count_stage2**: {eval_s2}",
        f"- **eligible_count**: {eligible}",
        "",
        "## Symbols",
        "",
        "| symbol | verdict | score | band | band_reason | stage_status | provider_status | primary_reason | price | expiration |",
        "|--------|--------|-------|------|-------------|--------------|----------------|----------------|-------|------------|",
    ]
    for s in symbols:
        br = (s.get("band_reason") or "")[:60].replace("|", " ")
        pr = (s.get("primary_reason") or "")[:40].replace("|", " ")
        lines.append(
            f"| {s.get('symbol', '')} | {s.get('verdict', '')} | {s.get('score', '')} | {s.get('band', '')} | {br} | "
            f"{s.get('stage_status', '')} | {s.get('provider_status', '')} | {pr} | {s.get('price', '')} | {s.get('expiration', '')} |"
        )

    # Top blockers: count FAIL_* / BLOCKED reasons
    from collections import Counter
    reasons: List[str] = []
    for s in symbols:
        pr = (s.get("primary_reason") or "").strip()
        if pr:
            reasons.append(pr[:80])
    top = Counter(reasons).most_common(10)
    lines.extend([
        "",
        "## Top blocker reasons (top 10)",
        "",
    ])
    for reason, count in top:
        lines.append(f"- {count}x: {reason}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _validate_api(
    store_ts: str,
    store_symbols: List[Dict[str, Any]],
    checks: List[Tuple[str, bool, str]],
    failures: List[str],
) -> None:
    """(6) GET system-health, decision/latest, universe, symbol-diagnostics; validate consistency."""
    # system-health: decision_store not CRITICAL
    status, body = _get(f"{API_BASE}/api/ui/system-health")
    if status != 200:
        checks.append(("GET /api/ui/system-health", False, f"status={status}"))
        failures.append("system-health non-200")
        return
    ds = (body or {}).get("decision_store") or {}
    crit = (ds.get("status") or "").upper() == "CRITICAL"
    checks.append(("system-health decision_store not CRITICAL", not crit, ds.get("reason") or "OK"))
    if crit:
        failures.append(f"decision_store CRITICAL: {ds.get('reason')}")

    # decision/latest
    status, dec = _get(f"{API_BASE}/api/ui/decision/latest?mode=LIVE")
    if status != 200:
        checks.append(("GET /api/ui/decision/latest", False, f"status={status}"))
        failures.append("decision/latest non-200")
    else:
        api_ts = (dec.get("artifact") or {}).get("metadata") or {}
        api_ts = api_ts.get("pipeline_timestamp")
        match = api_ts == store_ts
        checks.append(("decision/latest pipeline_timestamp == store", match, f"store={store_ts!r} api={api_ts!r}"))
        if not match and store_ts:
            failures.append("decision/latest pipeline_timestamp != store")

    # universe
    status, uni = _get(f"{API_BASE}/api/ui/universe")
    if status != 200:
        checks.append(("GET /api/ui/universe", False, f"status={status}"))
        failures.append("universe non-200")
    else:
        uni_ts = uni.get("updated_at") or uni.get("as_of") or (uni.get("metadata") or {}).get("pipeline_timestamp")
        match = uni_ts == store_ts
        checks.append(("universe timestamp == store", match, f"store={store_ts!r} uni={uni_ts!r}"))
        if not match and store_ts:
            failures.append("universe timestamp != store")

    # symbol-diagnostics for SPY, NVDA, AAPL
    for sym in ("SPY", "NVDA", "AAPL"):
        status, diag = _get(f"{API_BASE}/api/ui/symbol-diagnostics?symbol={sym}")
        if status == 404:
            # Symbol might not be in universe
            store_row = next((s for s in store_symbols if (s.get("symbol") or "").upper() == sym), None)
            if not store_row:
                checks.append((f"symbol-diagnostics {sym}", True, "symbol not in store (skip)"))
            else:
                checks.append((f"symbol-diagnostics {sym}", False, "404 but symbol in store"))
                failures.append(f"symbol-diagnostics {sym} 404 but in store")
            continue
        if status != 200:
            checks.append((f"symbol-diagnostics {sym}", False, f"status={status}"))
            continue
        store_row = next((s for s in store_symbols if (s.get("symbol") or "").upper() == sym), None)
        if not store_row:
            checks.append((f"symbol-diagnostics {sym} vs store", True, "symbol not in store"))
            continue
        score_ok = diag.get("composite_score") == store_row.get("score")
        band_ok = diag.get("confidence_band") == store_row.get("band")
        checks.append((f"symbol-diagnostics {sym} score/band == store", score_ok and band_ok,
                      f"diag score={diag.get('composite_score')} band={diag.get('confidence_band')} store score={store_row.get('score')} band={store_row.get('band')}"))
        if not (score_ok and band_ok):
            failures.append(f"symbol-diagnostics {sym} score/band != universe row")

    # GET /api/ui/alerts (green check: no error, optionally same pipeline_ts)
    status, alerts = _get(f"{API_BASE}/api/ui/alerts")
    checks.append(("GET /api/ui/alerts", status == 200, f"status={status}"))
    if status != 200:
        failures.append("alerts endpoint error")


def _write_report(
    report_path: Path,
    checks: List[Tuple[str, bool, str]],
    failures: List[str],
    store_path: Path,
    truth_path: Path,
    copy_path: Optional[Path],
) -> None:
    """Write out/market_live_validation_report.md."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Market Live Validation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Checklist",
        "",
    ]
    for name, ok, msg in checks:
        status = "PASS" if ok else "FAIL"
        lines.append(f"- [{status}] {name}")
        if msg and not ok:
            lines.append(f"  - {msg[:200]}")
    lines.extend([
        "",
        "## Result",
        "",
        f"**{'PASS' if not failures else 'FAIL'}** — " + (f"{len(failures)} failure(s): " + "; ".join(failures[:10]) if failures else "All checks passed."),
        "",
        "## Outputs",
        "",
        f"- Canonical store: `{store_path}`",
        f"- Truth table: `{truth_path}`",
    ])
    if copy_path:
        lines.append(f"- Canonical copy: `{copy_path}`")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main(use_api: bool = True) -> int:
    """Run validation. Return 0 pass, 2 validation fail, 3 runtime error."""
    checks: List[Tuple[str, bool, str]] = []
    failures: List[str] = []

    try:
        store_path = _get_store_path()
        out_dir = _out_dir()
        report_path = out_dir / "market_live_validation_report.md"
        truth_path = out_dir / "TRUTH_TABLE_V2.md"

        # (2) Run evaluation
        _run_evaluation(checks, failures)

        # (3) Read and validate store
        data = _read_store()
        if not data:
            checks.append(("Canonical store file exists", False, str(store_path)))
            failures.append("Canonical store file missing")
            _write_report(report_path, checks, failures, store_path, truth_path, None)
            print("VALIDATION FAIL: Store file missing")
            for c in checks:
                print(f"  [{'PASS' if c[1] else 'FAIL'}] {c[0]}")
            return 2
        checks.append(("Canonical store file exists", True, str(store_path)))

        _validate_store_invariants(data, failures, checks)

        # (4) Write canonical copy
        copy_path = _write_canonical_copy(data)
        checks.append(("Wrote decision_<ts>_canonical_copy.json", True, str(copy_path)))

        # (5) Truth table
        _generate_truth_table(data, truth_path)
        checks.append(("Wrote TRUTH_TABLE_V2.md", truth_path.exists(), str(truth_path)))

        # (6) API
        if use_api:
            meta = data.get("metadata") or {}
            store_ts = meta.get("pipeline_timestamp") or ""
            store_symbols = data.get("symbols") or []
            _validate_api(store_ts, store_symbols, checks, failures)

        # (7) Report
        _write_report(report_path, checks, failures, store_path, truth_path, copy_path)

        if failures:
            print("VALIDATION FAIL:", "; ".join(failures[:5]))
            for c in checks:
                print(f"  [{'PASS' if c[1] else 'FAIL'}] {c[0]}")
            return 2
        print("VALIDATION PASS: All checks passed.")
        return 0

    except Exception as e:
        print("RUNTIME ERROR:", e)
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Market live validation (ONE store v2)")
    p.add_argument("--no-api", action="store_true", help="Validate store only; do not hit API")
    args = p.parse_args()
    sys.exit(main(use_api=not args.no_api))
