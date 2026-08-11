# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Rebuild richer R51–R60 evidence pack (R61 recovery) + scaffolding for R61–R70."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{20,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*|ROBINHOOD_MCP_ACCESS_TOKEN\s*=\s*\S+|ORATS[A-Z_]*TOKEN\s*=\s*\S+|TUNNEL_TOKEN\s*=\s*\S+)"
)
ACCOUNT_RE = re.compile(r"\b\d{9,12}\b")


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _sanitize(text: str) -> str:
    text = SECRET_RE.sub("[REDACTED]", text)
    text = ACCOUNT_RE.sub(lambda m: ("*" * max(4, len(m.group(0)) - 4)) + m.group(0)[-4:], text)
    return text


def _run(cmd: list[str], cwd: Path) -> dict:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=600)
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout_tail": _sanitize((p.stdout or "")[-6000:]),
            "stderr_tail": _sanitize((p.stderr or "")[-3000:]),
        }
    except Exception as exc:
        return {"cmd": cmd, "error": type(exc).__name__, "detail": str(exc)[:400]}


def main() -> int:
    repo = _repo()
    short = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True).strip()
    out_dir = repo / "chakraOpsDropbox" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    quality_dir = repo / "out" / "verification" / "R61" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)

    backend = repo / "chakraops"
    py = backend / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path("python")

    steps = {
        "pytest_broker_safety": _run(
            [
                str(py),
                "-m",
                "pytest",
                "tests/test_r52_broker_write_denylist.py",
                "tests/test_r52_no_write_imports.py",
                "tests/test_r61_allowlist_hardening.py",
                "tests/test_r37_broker_read_only_nogo.py",
                "-q",
            ],
            backend,
        ),
        "pytest_r51_data": _run([str(py), "-m", "pytest", "tests/test_r51_data_platform.py", "-q"], backend),
    }
    (quality_dir / "quality_summary.json").write_text(json.dumps(steps, indent=2), encoding="utf-8")

    allowlist = (repo / "chakraops" / "config" / "robinhood_read_allowlist.json").read_text(encoding="utf-8")
    assert "review_equity_order" not in allowlist
    assert "place_equity_order" in allowlist  # denylist section

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program": "R61 evidence recovery for R51-R60 + hardening",
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "short": short,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "domain": "chakraops.cloud",
        "review_tools_excluded": True,
    }

    files: list[tuple[str, str]] = [
        ("repo_state.json", json.dumps(manifest, indent=2)),
        (
            "release_commits_r51_r60.txt",
            subprocess.check_output(["git", "log", "--oneline", "32e0449..c34cf39"], cwd=repo, text=True),
        ),
        ("quality/quality_summary.json", (quality_dir / "quality_summary.json").read_text(encoding="utf-8")),
        ("broker/robinhood_read_allowlist.json", _sanitize(allowlist)),
        (
            "broker/ROBINHOOD_TOOL_CLASSIFICATION.md",
            _sanitize(
                (repo / "docs" / "ai" / "releases" / "R52" / "ROBINHOOD_TOOL_CLASSIFICATION.md").read_text(
                    encoding="utf-8"
                )
            ),
        ),
    ]

    for rel in (
        "docs/ai/releases/R51/R51_ACCEPTANCE.md",
        "docs/ai/releases/R52/R52_ACCEPTANCE.md",
        "docs/ai/releases/R53/R53_ACCEPTANCE.md",
        "docs/ai/releases/R54/R54_ACCEPTANCE.md",
        "docs/ai/releases/R55/R55_ACCEPTANCE.md",
        "docs/ai/releases/R56/R56_ACCEPTANCE.md",
        "docs/ai/releases/R57/R57_ACCEPTANCE.md",
        "docs/ai/releases/R58/R58_ACCEPTANCE.md",
        "docs/ai/releases/R59/R59_ACCEPTANCE.md",
        "docs/ai/releases/R60/R60_ACCEPTANCE.md",
        "docs/ai/releases/R61/R61_ACCEPTANCE.md",
        "docs/ai/PROGRAM_STATUS.md",
        "docs/ai/releases/R61-R70/OWNER_ACTION_STATE.md",
    ):
        p = repo / rel
        if p.is_file():
            files.append((rel.replace("\\", "/"), _sanitize(p.read_text(encoding="utf-8", errors="ignore"))))

    zip_path = out_dir / f"ChakraOps_R61_HARDENED_EVIDENCE_{short}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / f"ChakraOps_R61_HARDENED_EVIDENCE_{short}.sha256").write_text(digest + "\n", encoding="utf-8")
    print(zip_path)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
