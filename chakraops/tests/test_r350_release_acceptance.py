# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 release acceptance manifest tests."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_manifest_exists_and_valid():
    path = REPO / "docs" / "ai" / "validation" / "R31_R35_ACCEPTANCE_MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["approved_branch"] == "release/R31-R35-program"
    assert data["authorization_base_commit"]
    assert len(data["authorized_implementation_paths"]) >= 20
    assert data["backup_guarantees"]["cleanup_dry_run_default"] is True


def test_required_scripts_exist():
    manifest = json.loads(
        (REPO / "docs" / "ai" / "validation" / "R31_R35_ACCEPTANCE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    for rel in manifest["required_powershell_scripts"]:
        assert (REPO / rel).exists(), rel


def test_validation_docs_exist():
    for name in (
        "R31_R35_ACCEPTANCE_CONTRACT.md",
        "R31_R35_ACCEPTANCE_MANIFEST.json",
        "R31_R35_SELF_REVIEW_CHECKLIST.md",
        "R31_R35_COWORK_UAT_HANDOFF.md",
    ):
        assert (REPO / "docs" / "ai" / "validation" / name).exists()


def test_scheduler_runbook_exists():
    assert (REPO / "chakraops" / "docs" / "RUNBOOK_SCHEDULER_OPERATIONS.md").exists()
