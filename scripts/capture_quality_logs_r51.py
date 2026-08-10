#!/usr/bin/env python3
"""R51 — Capture quality-gate evidence under out/verification/R51/quality/.

Runs ruff (if present), pytest --collect-only (plus optional small subset),
and frontend typecheck summary. Does not require full CI green to write logs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "chakraops"
FRONTEND = ROOT / "frontend"
OUT = ROOT / "out" / "verification" / "R51" / "quality"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = BACKEND / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)


def run(cmd: list[str], cwd: Path, timeout: int = 300) -> dict:
    print("+", " ".join(cmd), f"(cwd={cwd})")
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": p.returncode,
            "stdout_tail": (p.stdout or "")[-6000:],
            "stderr_tail": (p.stderr or "")[-3000:],
        }
    except FileNotFoundError as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": 127,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "missing": True,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": 124,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": "timeout",
        }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release": "R51",
        "gates": {},
    }

    # Ruff (optional if not installed)
    ruff = run([str(PY), "-m", "ruff", "check", "app", "tests"], BACKEND)
    if ruff.get("returncode") == 2 or "No module named ruff" in (
        (ruff.get("stderr_tail") or "") + (ruff.get("stdout_tail") or "")
    ):
        ruff = run(["ruff", "check", "app", "tests"], BACKEND)
    results["gates"]["ruff"] = ruff
    (OUT / "ruff.txt").write_text(
        (ruff.get("stdout_tail") or "") + "\n" + (ruff.get("stderr_tail") or ""),
        encoding="utf-8",
    )

    # Pytest collect-only (fast evidence of import/discovery)
    collect = run(
        [str(PY), "-m", "pytest", "--collect-only", "-q"],
        BACKEND,
        timeout=180,
    )
    results["gates"]["pytest_collect"] = collect
    (OUT / "pytest_collect.txt").write_text(
        (collect.get("stdout_tail") or "") + "\n" + (collect.get("stderr_tail") or ""),
        encoding="utf-8",
    )

    # Small focused subset
    subset = run(
        [str(PY), "-m", "pytest", "-q", "--tb=line", "tests/test_r51_data_platform.py"],
        BACKEND,
        timeout=180,
    )
    results["gates"]["pytest_r51_subset"] = subset
    (OUT / "pytest_r51_subset.txt").write_text(
        (subset.get("stdout_tail") or "") + "\n" + (subset.get("stderr_tail") or ""),
        encoding="utf-8",
    )

    # Frontend typecheck summary
    typecheck = run(["npm", "run", "typecheck"], FRONTEND, timeout=300)
    results["gates"]["frontend_typecheck"] = typecheck
    (OUT / "frontend_typecheck.txt").write_text(
        (typecheck.get("stdout_tail") or "") + "\n" + (typecheck.get("stderr_tail") or ""),
        encoding="utf-8",
    )

    summary = {
        "generated_at": results["generated_at"],
        "release": "R51",
        "returncodes": {k: v.get("returncode") for k, v in results["gates"].items()},
        "ruff_present": not ruff.get("missing")
        and "No module named ruff" not in ((ruff.get("stderr_tail") or "") + (ruff.get("stdout_tail") or "")),
        "notes": "Evidence capture only; see quality_report.json for tails.",
    }
    (OUT / "quality_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    # Non-zero only if focused R51 subset failed (evidence still written)
    return 0 if subset.get("returncode") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
