# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Build R61–R70 evidence ZIP (code-complete; remote UAT may still be pending owner)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{20,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*|ACCESS_TOKEN\s*=\s*\S+|TUNNEL_TOKEN\s*=\s*\S+|WEBHOOK\s*=\s*https?://\S+)"
)


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _sanitize(t: str) -> str:
    return SECRET_RE.sub("[REDACTED]", t)


def main() -> int:
    repo = _repo()
    short = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True).strip()
    out = repo / "chakraOpsDropbox" / "results"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "short": short,
        "domain": "chakraops.cloud",
        "status": "R61_R70_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE",
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "external_pending": [
            "VPS",
            "Cloudflare zone/NS/Access/Tunnel",
            "Robinhood production OAuth",
            "Slack webhook on VPS",
            "Codex/Cowork remote acceptance",
        ],
    }
    files = [("repo_state.json", json.dumps(manifest, indent=2))]
    files.append(
        (
            "commits.txt",
            subprocess.check_output(["git", "log", "--oneline", "c34cf39..HEAD"], cwd=repo, text=True),
        )
    )
    for rel in [
        "docs/ai/PROGRAM_STATUS.md",
        "docs/ai/releases/R61-R70/OWNER_ACTION_STATE.md",
        "docs/ai/releases/R61/R61_ACCEPTANCE.md",
        "docs/ai/releases/R62/R62_ACCEPTANCE.md",
        "docs/ai/releases/R63/R63_ACCEPTANCE.md",
        "docs/ai/releases/R64/R64_ACCEPTANCE.md",
        "docs/ai/releases/R65/R65_ACCEPTANCE.md",
        "docs/ai/releases/R66/R66_ACCEPTANCE.md",
        "docs/ai/releases/R67/R67_ACCEPTANCE.md",
        "docs/ai/releases/R68/R68_ACCEPTANCE.md",
        "docs/ai/releases/R69/R69_ACCEPTANCE.md",
        "docs/ai/releases/R70/R70_ACCEPTANCE.md",
        "docs/ai/releases/R70/CODEX_FINAL_REVIEW_HANDOFF.md",
        "docs/ai/releases/R70/COWORK_FINAL_REMOTE_UAT_HANDOFF.md",
        "chakraops/config/robinhood_read_allowlist.json",
        "deploy/docker-compose.prod.yml",
        "deploy/.env.prod.example",
    ]:
        p = repo / rel
        if p.is_file():
            files.append((rel.replace("\\", "/"), _sanitize(p.read_text(encoding="utf-8", errors="ignore"))))

    zip_path = out / f"ChakraOps_R61_R70_FINAL_EVIDENCE_{short}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, c in files:
            zf.writestr(n, c)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out / f"ChakraOps_R61_R70_FINAL_EVIDENCE_{short}.sha256").write_text(digest + "\n", encoding="utf-8")
    print(zip_path)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
