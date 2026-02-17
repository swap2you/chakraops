#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Sanity script for one-pipeline runbook. Store-first verification.

1) Runs run_and_save.py --symbols SPY,AAPL --output-dir out (populates canonical store)
2) Reads canonical store file (<repo>/out/decision_latest.json)
3) Calls local API (assume server running): decision/latest, universe, symbol-diagnostics
4) Verifies invariants (store-first consistency). Exit 2 on SANITY FAIL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO / ".env")
except ImportError:
    pass

API_BASE = "http://127.0.0.1:8000"


def _get_store_path() -> Path:
    from app.core.eval.evaluation_store_v2 import get_decision_store_path
    return get_decision_store_path()


def _read_store() -> dict | None:
    path = _get_store_path()
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get(url: str) -> tuple[int, dict]:
    import urllib.request
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def _post(url: str, data: dict) -> tuple[int, dict]:
    import urllib.request
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode())


def main(skip_api: bool = False) -> int:
    failures: list[str] = []
    checks: list[tuple[str, bool, str]] = []

    # 0) Run run_and_save to populate canonical store
    try:
        result = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "run_and_save.py"), "--symbols", "SPY,AAPL", "--output-dir", "out"],
            cwd=str(_REPO),
            env={**os.environ, "PYTHONPATH": str(_REPO)},
            capture_output=True,
            text=True,
            timeout=180,
        )
        ok = result.returncode == 0
        checks.append(("run_and_save.py --symbols SPY,AAPL --output-dir out", ok, result.stderr or result.stdout))
        if not ok:
            failures.append("run_and_save failed")
            print("SANITY FAIL: run_and_save failed")
            for name, o, msg in checks:
                print(f"  [{'PASS' if o else 'FAIL'}] {name}")
            return 2
    except subprocess.TimeoutExpired:
        failures.append("run_and_save timed out")
        return 2
    except Exception as e:
        failures.append(str(e))
        return 2

    # 1) Read canonical store
    store = _read_store()
    if not store:
        failures.append("Canonical store file not found")
        print("SANITY FAIL: Store file not found at", _get_store_path())
        return 2
    store_meta = store.get("metadata") or store
    store_ts = store_meta.get("pipeline_timestamp")
    store_ver = store_meta.get("artifact_version")
    v2_ok = store_ver == "v2"
    checks.append(("Store file exists, artifact_version=v2", v2_ok, f"version={store_ver}"))
    if not v2_ok:
        failures.append("Store artifact_version not v2")

    if skip_api:
        _report(checks, failures)
        all_ok = len(failures) == 0
        return 2 if not all_ok else 0

    # 2) GET /api/ui/decision/latest
    try:
        status, body = _get(f"{API_BASE}/api/ui/decision/latest?mode=LIVE")
        ver = body.get("artifact_version") if status == 200 else None
        artifact = body.get("artifact") or {}
        api_meta = artifact.get("metadata") or artifact
        api_ts = api_meta.get("pipeline_timestamp")
        ok = status == 200 and ver == "v2"
        checks.append(("GET /api/ui/decision/latest artifact_version=v2", ok, f"status={status} version={ver}"))
        if ok and store_ts and api_ts and store_ts != api_ts:
            failures.append("decision/latest metadata.pipeline_timestamp != store pipeline_timestamp")
            checks.append(("Store vs API pipeline_timestamp match", False, f"store={store_ts} api={api_ts}"))
        elif ok and store_ts and api_ts:
            checks.append(("Store vs API pipeline_timestamp match", True, f"ts={store_ts}"))
    except Exception as e:
        checks.append(("GET /api/ui/decision/latest", False, str(e)))
        failures.append(f"API: {e}")
        print("SANITY FAIL: Cannot reach API (is server running?)")
        _report(checks, failures)
        return 2

    # 3) GET /api/ui/universe
    try:
        status, body = _get(f"{API_BASE}/api/ui/universe")
        symbols = body.get("symbols", []) if status == 200 else []
        bad = [s for s in symbols if s.get("band") is None or s.get("band") == ""]
        ok = status == 200 and len(bad) == 0
        checks.append(("GET /api/ui/universe: all rows have band", ok, f"status={status} band_null={len(bad)}"))
        if not ok:
            failures.append("universe missing band")
    except Exception as e:
        checks.append(("GET /api/ui/universe", False, str(e)))
        failures.append(str(e))

    # 4) Universe row for SPY vs decision/latest symbols row
    try:
        _, uni = _get(f"{API_BASE}/api/ui/universe")
        _, dec = _get(f"{API_BASE}/api/ui/decision/latest?mode=LIVE")
        uni_symbols = uni.get("symbols", [])
        dec_symbols = (dec.get("artifact") or {}).get("symbols", [])
        spy_uni = next((s for s in uni_symbols if s.get("symbol") == "SPY"), None)
        spy_dec = next((s for s in dec_symbols if s.get("symbol") == "SPY"), None)
        if spy_uni and spy_dec:
            score_ok = spy_uni.get("score") == spy_dec.get("score")
            band_ok = spy_uni.get("band") == spy_dec.get("band")
            ok = score_ok and band_ok
            checks.append(("Universe SPY score/band == decision symbols SPY", ok,
                          f"uni score={spy_uni.get('score')} band={spy_uni.get('band')} dec score={spy_dec.get('score')} band={spy_dec.get('band')}"))
            if not ok:
                failures.append("SPY universe vs decision mismatch")
        else:
            checks.append(("Universe SPY vs decision SPY", True, "SPY not in results (skip)"))
    except Exception as e:
        checks.append(("Universe vs decision SPY", False, str(e)))
        failures.append(str(e))

    # 5) symbol-diagnostics for SPY vs store
    try:
        status, diag = _get(f"{API_BASE}/api/ui/symbol-diagnostics?symbol=SPY")
        if status == 200 and diag:
            store_symbols = store.get("symbols", [])
            spy_store = next((s for s in store_symbols if s.get("symbol") == "SPY"), None)
            if spy_store:
                score_ok = diag.get("composite_score") == spy_store.get("score")
                band_ok = diag.get("confidence_band") == spy_store.get("band")
                verdict_ok = diag.get("verdict") == spy_store.get("verdict")
                ok = score_ok and band_ok and verdict_ok
                checks.append(("symbol-diagnostics SPY vs store SPY", ok,
                              f"diag score={diag.get('composite_score')} band={diag.get('confidence_band')} store score={spy_store.get('score')} band={spy_store.get('band')}"))
                if not ok:
                    failures.append("SPY symbol-diagnostics vs store mismatch")
            else:
                checks.append(("symbol-diagnostics SPY vs store", True, "SPY not in store"))
        else:
            checks.append(("symbol-diagnostics SPY", status == 200, f"status={status}"))
    except Exception as e:
        checks.append(("symbol-diagnostics SPY", False, str(e)))
        failures.append(str(e))

    all_ok = len(failures) == 0
    _report(checks, failures)
    if not all_ok:
        print("SANITY FAIL: One or more invariants violated. See above.")
        return 2
    print("PASS: All sanity checks passed.")
    return 0


def _report(checks: list, failures: list) -> None:
    print("=" * 60)
    print("Sanity: ONE pipeline / ONE store / store-first verification")
    print("=" * 60)
    for name, ok, msg in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok and msg:
            print(f"       {msg}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-api", action="store_true", help="Skip API checks (file invariants only)")
    args = p.parse_args()
    sys.exit(main(skip_api=args.no_api))
