#!/usr/bin/env python3
"""R50 — Build redacted final evidence ZIP for R41–R50."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROPBOX_RESULTS = ROOT / "chakraOpsDropbox" / "results"
SECRET_PATTERNS = [
    re.compile(r"(?i)orats[_\-]?api[_\-]?token\s*=\s*\S+"),
    re.compile(r"(?i)slack[_\-]?webhook[^\s\"']+"),
    re.compile(r"(?i)authorization:\s*bearer\s+\S+"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)x-ui-key[\"']?\s*[:=]\s*[\"']?[a-zA-Z0-9_\-]{8,}"),
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(ROOT), text=True).strip()


def short_sha() -> str:
    return git("rev-parse", "--short", "HEAD")


def collect_files() -> list[tuple[Path, str]]:
    """Return (absolute_path, arcname) pairs."""
    pairs: list[tuple[Path, str]] = []

    def add(path: Path, arc: str) -> None:
        if path.is_file():
            pairs.append((path, arc))

    def add_tree(base: Path, arc_prefix: str) -> None:
        if not base.exists():
            return
        for p in base.rglob("*"):
            if p.is_file():
                # skip secrets / env
                if p.name == ".env" or p.suffix in {".pem", ".key"}:
                    continue
                if "node_modules" in p.parts or ".venv" in p.parts:
                    continue
                rel = p.relative_to(base).as_posix()
                pairs.append((p, f"{arc_prefix}/{rel}"))

    sha = short_sha()
    state = {
        "program": "CHAKRAOPS R41-R50 OPERATOR PRODUCTIONIZATION",
        "status": "R41_R50_TECHNICALLY_COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE",
        "final_sha": git("rev-parse", "HEAD"),
        "short_sha": sha,
        "origin_main": git("rev-parse", "origin/main"),
        "clean_tree": git("status", "--porcelain") == "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commits": git("log", "--oneline", "e0813a8..HEAD").splitlines(),
        "safety": {
            "manual_only": True,
            "trade_execution": False,
            "scheduler_default": False,
            "broker_write": False,
            "orats_hist_options": "EXTERNAL_ENTITLEMENT_GAP",
        },
    }
    tmp = ROOT / "out" / "verification" / "R50" / "repo_state.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    add(tmp, "repo_state.json")

    for rel in [
        "docs/ai/PROGRAM_STATUS.md",
        "docs/ai/MASTER_PROGRAM_R41_R50_REQUIREMENTS.md",
        "docs/ai/validation/R40_ACCEPTANCE_MANIFEST.json",
    ]:
        add(ROOT / rel, rel)

    for release in ["R41", "R42", "R43", "R44", "R45", "R46", "R47", "R48", "R49", "R50"]:
        add_tree(ROOT / "docs" / "ai" / "releases" / release, f"acceptance/{release}")
        add_tree(ROOT / "out" / "verification" / release, f"verification/{release}")

    add_tree(ROOT / "docs" / "ai" / "releases" / "R41", "screen_contract")
    return pairs


def scan_text(data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    hits = []
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def main() -> None:
    DROPBOX_RESULTS.mkdir(parents=True, exist_ok=True)
    sha = short_sha()
    zip_path = DROPBOX_RESULTS / f"ChakraOps_R41_R50_FINAL_EVIDENCE_{sha}.zip"
    pairs = collect_files()
    secret_findings = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arc in pairs:
            data = src.read_bytes()
            hits = scan_text(data)
            if hits:
                secret_findings.append({"file": arc, "patterns": hits})
                continue  # omit rather than ship secrets
            zf.writestr(arc, data)
        manifest = {
            "files": [arc for _, arc in pairs if not any(s["file"] == arc for s in secret_findings)],
            "omitted_secret_suspects": secret_findings,
            "sha": sha,
        }
        zf.writestr("EVIDENCE_MANIFEST.json", json.dumps(manifest, indent=2))

    # CRC test
    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        names = zf.namelist()
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    meta = {
        "zip": str(zip_path),
        "sha256": digest,
        "crc_ok": bad is None,
        "file_count": len(names),
        "required_ok": "repo_state.json" in names and "EVIDENCE_MANIFEST.json" in names,
    }
    (ROOT / "out" / "verification" / "R50" / "evidence_zip_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    if not meta["crc_ok"] or not meta["required_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
