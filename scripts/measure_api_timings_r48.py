#!/usr/bin/env python3
"""R48 — Measure representative API timings (warm). No secrets printed."""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("CHAKRAOPS_BACKEND_URL", "http://127.0.0.1:18800").rstrip("/")
OUT = Path(os.environ.get("CHAKRAOPS_TIMING_OUT", "out/verification/R48"))
UI_KEY = os.environ.get("UI_API_KEY") or os.environ.get("VITE_UI_KEY") or ""

ENDPOINTS = [
    ("GET", "/api/healthz", "health"),
    ("GET", "/api/operations/status", "ops_status"),
    ("GET", "/api/ui/system-health", "system_health"),
    ("GET", "/api/ui/decision/latest", "decision_latest"),
    ("GET", "/api/ui/action-needed", "action_needed"),
    ("GET", "/api/ui/broker/status", "broker_status"),
]


def fetch(method: str, path: str) -> tuple[int, float, int]:
    req = urllib.request.Request(BASE + path, method=method)
    if UI_KEY:
        req.add_header("x-ui-key", UI_KEY)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            ms = (time.perf_counter() - t0) * 1000
            return resp.status, ms, len(body)
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        return e.code, ms, 0
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        return 0, ms, 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # warm
    for method, path, _ in ENDPOINTS:
        fetch(method, path)
    rows = []
    for method, path, name in ENDPOINTS:
        status, ms, size = fetch(method, path)
        rows.append(
            {
                "name": name,
                "method": method,
                "path": path,
                "status": status,
                "latency_ms": round(ms, 1),
                "bytes": size,
                "budget_hint": "<1000 health/status; <2000 read-model; <3000 page data",
            }
        )
    csv_path = OUT / "api_timings.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "backend": BASE,
        "rows": rows,
        "notes": [
            "Read-only endpoints only; no full-universe eval triggered.",
            "Scheduler must remain disabled by default.",
        ],
    }
    (OUT / "api_timings.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path}")
    for r in rows:
        print(f"{r['name']}: {r['latency_ms']}ms status={r['status']}")


if __name__ == "__main__":
    main()
