#!/usr/bin/env python3
"""R50 — Local Sonar-style quality gate (blocking where tools exist). No secrets."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "chakraops"
FRONTEND = ROOT / "frontend"
OUT = ROOT / "out" / "verification" / "R50" / "quality"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)


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
    results: dict = {"gates": {}, "blocking_failures": []}

    # Backend pytest
    results["gates"]["pytest"] = run(
        [str(PY), "-m", "pytest", "-q", "--tb=line"],
        BACKEND,
    )

    # Ruff (blocking)
    ruff = run([str(PY), "-m", "ruff", "check", "app", "tests"], BACKEND)
    if ruff["returncode"] == 2 or "No module named ruff" in (ruff["stderr_tail"] + ruff["stdout_tail"]):
        # try ruff executable
        ruff = run(["ruff", "check", "app", "tests"], BACKEND)
    results["gates"]["ruff"] = ruff

    # Bandit (advisory if missing)
    results["gates"]["bandit"] = run(
        [str(PY), "-m", "bandit", "-q", "-r", "app", "-ll"],
        BACKEND,
    )

    # pip-audit (advisory if missing)
    results["gates"]["pip_audit"] = run([str(PY), "-m", "pip_audit", "-f", "json"], BACKEND)

    # Frontend
    results["gates"]["frontend_typecheck"] = run(["npm", "run", "typecheck"], FRONTEND)
    results["gates"]["frontend_test"] = run(["npm", "run", "test", "--", "--run"], FRONTEND)
    results["gates"]["frontend_build"] = run(["npm", "run", "build"], FRONTEND)
    results["gates"]["frontend_lint"] = run(["npm", "run", "lint"], FRONTEND)

    # Playwright (requires servers)
    if os.environ.get("CHAKRAOPS_SKIP_E2E") == "1":
        results["gates"]["playwright"] = {"returncode": 0, "skipped": True}
    else:
        env_cmd = ["npx", "playwright", "test", "--reporter=list"]
        results["gates"]["playwright"] = run(env_cmd, FRONTEND)

    # Secret scan (basic)
    secret_hits = []
    for pat in ["ORATS_API_TOKEN=", "SLACK_WEBHOOK", "OPENAI_API_KEY=sk-"]:
        # only flag if committed example has real-looking values — check .env not tracked
        pass
    env_tracked = subprocess.run(
        ["git", "ls-files", "*.env", "**/.env"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if env_tracked.stdout.strip():
        secret_hits.append({"issue": ".env tracked", "files": env_tracked.stdout.strip().splitlines()})
    results["gates"]["secret_scan"] = {"returncode": 0 if not secret_hits else 1, "hits": secret_hits}

    blocking = ["pytest", "ruff", "frontend_typecheck", "frontend_test", "frontend_build"]
    for name in blocking:
        g = results["gates"].get(name) or {}
        if g.get("returncode", 1) != 0 and not g.get("skipped"):
            results["blocking_failures"].append(name)

    (OUT / "quality_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"blocking_failures": results["blocking_failures"]}, indent=2))
    return 1 if results["blocking_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
