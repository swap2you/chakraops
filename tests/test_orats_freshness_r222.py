# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Repository-root identity test for the allowlisted ORATS freshness path.

This module is ``tests/test_orats_freshness_r222.py``. It is not
``backend/tests/test_orats_freshness_r222.py`` and it does not exec that
suite. Pytest stdout, stderr, and JSON result files are artifacts, not
this module.

Mission rows below are the approved successor contract. They are not a
NEEWA registry receipt, not a write lease, and not charter approval.
``RELEASE_CANDIDATE.md`` stays out of this repository; its absence does
not mark REQ-004 passed. The controller owns that artifact.

Hash methods, both SHA-256:
- file bytes: exact bytes of a path
- git diff: stdout bytes of ``git diff --no-ext-diff --no-color -- <paths>``
  Untracked paths are absent from that diff; use the file-byte hash for them.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT_TEST = Path(__file__).resolve()
BACKEND_TEST = REPO / "backend" / "tests" / "test_orats_freshness_r222.py"
CANONICAL_CHECKOUT = Path(r"C:\Users\swap2\NEEWA-Personal\projects\ChakraOps")

FILE_HASH_METHOD = "sha256-of-exact-file-bytes"
DIFF_HASH_METHOD = "sha256-of-git-diff-no-ext-diff-no-color-stdout-bytes"

ARTIFACT_NAMES = frozenset(
    {"pytest_stdout.txt", "pytest_stderr.txt", "test-results.json"}
)
FRESHNESS_PATHS = frozenset(
    {
        "backend/app/api/data_health.py",
        "backend/app/core/eval/evaluation_store.py",
        "backend/tests/test_orats_freshness_r222.py",
        "tests/test_orats_freshness_r222.py",
    }
)
# Only this path may be dirty while the root module is still untracked.
ALLOWED_DIRTY = frozenset({"tests/test_orats_freshness_r222.py"})

REQ004_SATISFIED_BY_ABSENCE = False
REQUIREMENT_MARKS = {
    "REQ-001": "SUCCESSOR_CONTRACT",
    "REQ-004": "CONTROLLER_OWNED_NOT_A_PRODUCT_PASS",
}
WORKER_COMPLETION_IS_CHARTER_APPROVAL = False
WRITE_LEASE_PROVED_BY_THIS_FILE = False
REOPEN_FAILED_JOB = False
REGISTRY_RECEIPT_PRESENT_IN_REPO = False
MISSION_AUTHORITY = "approved_work_package_contract"

PREDECESSOR = "MISSION-20261008T133401Z-55B99A8F"
FAILED_JOB = "JOB-20261008T213834Z-B2D93884-AUTO"
FAILED_JOB_REASON = "CHILD_TIMEOUT"
PRESERVED_MISSIONS = {
    "MISSION-20261007T204850Z-C2E85D13": ("FAILED", "MAX_REPAIR_CYCLES"),
    "MISSION-20261008T015300Z-A9B1DD10": ("BLOCKED", "A2_OWNER_GATE"),
    "MISSION-20261008T133401Z-55B99A8F": ("FAILED", "IDENTICAL_FAILURE_NO_NEW_EVIDENCE"),
}

BACKEND_FRESHNESS_TESTS = (
    "test_malformed_orats_timestamp_is_unknown",
    "test_future_orats_timestamp_is_unknown",
    "test_timezone_less_orats_timestamp_is_unknown",
    "test_provider_connectivity_matches_unknown_freshness",
    "test_persisted_state_read_uses_temp_dir_without_creating_it",
    "test_get_orats_freshness_state_error_when_no_timestamp",
    "test_loopback_health_get_only",
)

LOOPBACK_HEALTHZ = (
    "http://127.0.0.1:18800/api/healthz",
    "http://127.0.0.1:18873/api/healthz",
)
LOOPBACK_HEALTH = "http://127.0.0.1:18800/health"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_diff_stdout(paths: list[str]) -> bytes:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-color", "--", *paths],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    return completed.stdout


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def parse_porcelain_path(line: str) -> str:
    raw = line.split(" -> ", 1)[1] if " -> " in line else line[3:]
    return raw.strip().strip('"').replace("\\", "/")


def classify_dirty_path(path: str) -> str:
    name = Path(path).name
    if name in ARTIFACT_NAMES:
        return "pytest_artifact"
    if path == "tests/test_orats_freshness_r222.py":
        return "root_test"
    if path == "backend/tests/test_orats_freshness_r222.py":
        return "backend_test"
    if path in FRESHNESS_PATHS or "orats" in path.lower():
        return "other_orats"
    return "unrelated"


def http_get_json(url: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload


def test_root_module_is_not_the_backend_suite():
    assert ROOT_TEST.parent == REPO / "tests"
    assert ROOT_TEST.name == BACKEND_TEST.name
    assert BACKEND_TEST.is_file()
    assert ROOT_TEST.resolve() != BACKEND_TEST.resolve()
    assert sha256_file(ROOT_TEST) != sha256_file(BACKEND_TEST)


def test_pytest_artifacts_are_not_this_module():
    for name in ARTIFACT_NAMES:
        artifact = REPO / name
        assert artifact.resolve() != ROOT_TEST.resolve()
        assert artifact.suffix != ".py"
        assert not artifact.is_file()


def test_product_repo_absence_is_not_req004_pass():
    assert not (REPO / "RELEASE_CANDIDATE.md").exists()
    assert REQ004_SATISFIED_BY_ABSENCE is False
    assert REQUIREMENT_MARKS["REQ-004"] == "CONTROLLER_OWNED_NOT_A_PRODUCT_PASS"
    assert REQUIREMENT_MARKS["REQ-004"] != "PASS"


def test_preserved_missions_stay_terminal():
    assert PRESERVED_MISSIONS[PREDECESSOR] == (
        "FAILED",
        "IDENTICAL_FAILURE_NO_NEW_EVIDENCE",
    )
    assert PRESERVED_MISSIONS["MISSION-20261007T204850Z-C2E85D13"] == (
        "FAILED",
        "MAX_REPAIR_CYCLES",
    )
    assert PRESERVED_MISSIONS["MISSION-20261008T015300Z-A9B1DD10"] == (
        "BLOCKED",
        "A2_OWNER_GATE",
    )
    for status, _detail in PRESERVED_MISSIONS.values():
        assert status in {"FAILED", "BLOCKED"}


def test_workspace_docs_do_not_relabel_preserved_missions():
    for directory in (REPO / "docs", REPO / "requirements"):
        for path in directory.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for mission in PRESERVED_MISSIONS:
                if mission not in text:
                    continue
                window = text[text.index(mission) : text.index(mission) + 500]
                assert "SUCCESS" not in window
                assert "PASSED" not in window
    contract = (REPO / "docs" / "NEEWA.md").read_text(encoding="utf-8")
    assert "MISSION-20261007T185227Z-C29E3404" in contract
    assert "MISSION-20261007T204742Z-1FFC322B" in contract


def test_contract_is_not_registry_receipt_or_charter_approval():
    assert REGISTRY_RECEIPT_PRESENT_IN_REPO is False
    assert MISSION_AUTHORITY == "approved_work_package_contract"
    assert WRITE_LEASE_PROVED_BY_THIS_FILE is False
    assert WORKER_COMPLETION_IS_CHARTER_APPROVAL is False
    assert REOPEN_FAILED_JOB is False
    assert FAILED_JOB == "JOB-20261008T213834Z-B2D93884-AUTO"
    assert FAILED_JOB_REASON == "CHILD_TIMEOUT"


def test_candidate_hash_methods_are_sha256():
    file_digest = sha256_file(ROOT_TEST)
    diff_digest = sha256_bytes(
        git_diff_stdout(
            [
                "tests/test_orats_freshness_r222.py",
                "backend/tests/test_orats_freshness_r222.py",
            ]
        )
    )
    assert FILE_HASH_METHOD == "sha256-of-exact-file-bytes"
    assert DIFF_HASH_METHOD == "sha256-of-git-diff-no-ext-diff-no-color-stdout-bytes"
    assert len(file_digest) == 64
    assert len(diff_digest) == 64
    assert file_digest != sha256_file(BACKEND_TEST)


def test_dirty_orats_paths_are_classified():
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = parse_porcelain_path(line)
        kind = classify_dirty_path(path)
        if kind == "unrelated":
            continue
        assert kind != "pytest_artifact", path
        assert kind == "root_test", path
        assert path in ALLOWED_DIRTY


def test_backend_freshness_suite_remains_present():
    text = BACKEND_TEST.read_text(encoding="utf-8")
    for name in BACKEND_FRESHNESS_TESTS:
        assert f"def {name}" in text
    assert 'Path(__file__).resolve().parent.parent.name == "backend"' in text


def test_canonical_checkout_and_get_only_loopback_identity():
    assert REPO.resolve() == CANONICAL_CHECKOUT.resolve()
    head = git_head()
    for url in LOOPBACK_HEALTHZ:
        status, body = http_get_json(url)
        assert status == 200
        assert body.get("ok") is True
        assert body.get("status") == "ok"
        assert "build_id" not in body
    status, health = http_get_json(LOOPBACK_HEALTH)
    assert status == 200
    assert health.get("ok") is True
    assert health.get("status") == "healthy"
    assert health.get("build_id") == head
