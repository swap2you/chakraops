#!/usr/bin/env python3
"""R70 — Local Sonar-style quality gate (blocking where tools exist). No secrets.

Supersedes scripts/quality_gate_r50.py naming (R70-DEF-074). The R50 script
remains as a thin wrapper that delegates here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "chakraops"
FRONTEND = ROOT / "frontend"
OUT = ROOT / "out" / "verification" / "R70" / "quality"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = BACKEND / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)

# Pin critical regressions for R40.1–R70 (mirrors .github/workflows/ci.yml).
CRITICAL_TESTS = [
    "tests/test_r401_scheduler_defaults.py",
    "tests/test_r401_eval_concurrency.py",
    "tests/test_r401_wheel_cash.py",
    "tests/test_r41_r401_regressions.py",
    "tests/test_r42_ticket_queue.py",
    "tests/test_r48_read_no_eval.py",
    "tests/test_r61_allowlist_hardening.py",
    "tests/test_r62_postgres_production.py",
    "tests/test_r63_compose_golive.py",
    "tests/test_r52_snapshot_fail_closed.py",
    "tests/test_r52_broker_write_denylist.py",
    "tests/test_r54_monitor_signals.py",
    "tests/test_r58_r59_advisor_backtest.py",
    "tests/test_r64_r69_golive.py",
    "tests/test_r70_finance_eval_batch.py",
    "tests/test_r70_def072_startup.py",
    "tests/test_r70_ai_grounding.py",
    "tests/test_r70_persistence_honesty.py",
]


def run(cmd: list[str], cwd: Path) -> dict:
    print("+", " ".join(cmd), f"(cwd={cwd})")
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "returncode": p.returncode,
        "stdout_tail": (p.stdout or "")[-4000:],
        "stderr_tail": (p.stderr or "")[-2000:],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {"gates": {}, "blocking_failures": [], "gate_name": "quality_gate_r70"}

    results["gates"]["pytest"] = run(
        [str(PY), "-m", "pytest", "-q", "--tb=line"],
        BACKEND,
    )
    results["gates"]["pytest_critical_r61_r70"] = run(
        [str(PY), "-m", "pytest", *CRITICAL_TESTS, "-q", "--tb=short"],
        BACKEND,
    )

    ruff = run([str(PY), "-m", "ruff", "check", "app", "tests"], BACKEND)
    if ruff["returncode"] == 2 or "No module named ruff" in (ruff["stderr_tail"] + ruff["stdout_tail"]):
        ruff = run(["ruff", "check", "app", "tests"], BACKEND)
    results["gates"]["ruff"] = ruff

    results["gates"]["bandit"] = run(
        [str(PY), "-m", "bandit", "-q", "-r", "app", "-ll"],
        BACKEND,
    )
    results["gates"]["pip_audit"] = run([str(PY), "-m", "pip_audit", "-f", "json"], BACKEND)

    results["gates"]["frontend_typecheck"] = run(["npm", "run", "typecheck"], FRONTEND)
    results["gates"]["frontend_test"] = run(["npm", "run", "test", "--", "--run"], FRONTEND)
    results["gates"]["frontend_build"] = run(["npm", "run", "build"], FRONTEND)
    results["gates"]["frontend_lint"] = run(["npm", "run", "lint"], FRONTEND)

    if os.environ.get("CHAKRAOPS_SKIP_E2E") == "1":
        results["gates"]["playwright"] = {"returncode": 0, "skipped": True}
    else:
        results["gates"]["playwright"] = run(
            ["npx", "playwright", "test", "--reporter=list"],
            FRONTEND,
        )

    secret_hits = []
    env_tracked = subprocess.run(
        ["git", "ls-files", "*.env", "**/.env"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if env_tracked.stdout.strip():
        secret_hits.append({"issue": ".env tracked", "files": env_tracked.stdout.strip().splitlines()})
    results["gates"]["secret_scan"] = {"returncode": 0 if not secret_hits else 1, "hits": secret_hits}

    blocking = [
        "pytest",
        "pytest_critical_r61_r70",
        "ruff",
        "frontend_typecheck",
        "frontend_test",
        "frontend_build",
    ]
    for name in blocking:
        g = results["gates"].get(name) or {}
        if g.get("returncode", 1) != 0 and not g.get("skipped"):
            results["blocking_failures"].append(name)

    (OUT / "quality_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"blocking_failures": results["blocking_failures"]}, indent=2))
    return 1 if results["blocking_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
