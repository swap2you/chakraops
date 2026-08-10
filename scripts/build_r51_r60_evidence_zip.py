# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Build redacted R51–R60 final evidence ZIP under chakraOpsDropbox/results/."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{20,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*|ROBINHOOD_MCP_ACCESS_TOKEN\s*=\s*\S+|ORATS[A-Z_]*TOKEN\s*=\s*\S+)"
)
ACCOUNT_RE = re.compile(r"\b\d{9,12}\b")


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _sanitize(text: str) -> str:
    text = SECRET_RE.sub("[REDACTED]", text)
    text = ACCOUNT_RE.sub(lambda m: ("*" * max(4, len(m.group(0)) - 4)) + m.group(0)[-4:], text)
    return text


def main() -> int:
    repo = _repo()
    short = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True).strip()
    out_dir = repo / "chakraOpsDropbox" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"ChakraOps_R51_R60_FINAL_EVIDENCE_{short}.zip"

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "short": short,
        "status": "R51_R60_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE",
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "external_gaps": [
            "ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER",
            "DOMAIN_VPS_BINDING_EXTERNAL",
            "ORATS_HIST_OPTIONS_EXTERNAL_ENTITLEMENT_GAP",
            "ORATS_BACKTEST_ENTITLEMENT_GAP_POSSIBLE",
        ],
    }

    files: list[tuple[str, str]] = [
        ("repo_state.json", json.dumps(manifest, indent=2)),
        (
            "release_commits.txt",
            subprocess.check_output(
                ["git", "log", "--oneline", "32e0449..HEAD"],
                cwd=repo,
                text=True,
            ),
        ),
    ]

    for rel in (
        "docs/ai/releases/R51/R51_ACCEPTANCE.md",
        "docs/ai/releases/R52/R52_ACCEPTANCE.md",
        "docs/ai/releases/R52/ROBINHOOD_TOOL_CLASSIFICATION.md",
        "docs/ai/releases/R53/R53_ACCEPTANCE.md",
        "docs/ai/releases/R54/R54_ACCEPTANCE.md",
        "docs/ai/releases/R55/R55_ACCEPTANCE.md",
        "docs/ai/releases/R56/R56_ACCEPTANCE.md",
        "docs/ai/releases/R57/R57_ACCEPTANCE.md",
        "docs/ai/releases/R57/DOMAIN_VPS_BINDING_EXTERNAL.md",
        "docs/ai/releases/R58/R58_ACCEPTANCE.md",
        "docs/ai/releases/R59/R59_ACCEPTANCE.md",
        "docs/ai/releases/R60/R60_ACCEPTANCE.md",
        "chakraops/config/robinhood_read_allowlist.json",
        "docs/ai/PROGRAM_STATUS.md",
    ):
        p = repo / rel
        if p.is_file():
            files.append((rel.replace("\\", "/"), _sanitize(p.read_text(encoding="utf-8", errors="ignore"))))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / f"ChakraOps_R51_R60_FINAL_EVIDENCE_{short}.sha256").write_text(digest + "\n", encoding="utf-8")
    print(zip_path)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
