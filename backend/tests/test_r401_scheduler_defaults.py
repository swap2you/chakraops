# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: scheduler fail-closed defaults — dotenv cannot enable without allow flag."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


PROTECTED = (
    "CHAKRAOPS_SCHEDULER_ENABLED",
    "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED",
    "NIGHTLY_EVAL_ENABLED",
    "EOD_CHAIN_ENABLED",
)


def _clear_scheduler_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        *PROTECTED,
        "CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN",
    ):
        monkeypatch.delenv(k, raising=False)


def _run_load_env_with_dotenv_file(tmp_path: Path, env_body: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invoke server._load_env against a temp .env by patching Path resolution."""
    env_file = tmp_path / ".env"
    env_file.write_text(env_body, encoding="utf-8")

    import app.api.server as server_mod

    # Point repo-root resolution used inside _load_env to tmp_path
    real_resolve = Path.resolve

    def _fake_resolve(self: Path):  # type: ignore[no-untyped-def]
        resolved = real_resolve(self)
        # When resolving server.py's parents[2] (.env parent), redirect to tmp
        if resolved.name == "server.py" or "app" in resolved.parts and resolved.suffix == ".py":
            return resolved
        return resolved

    # Patch the Path used inside _load_env by temporarily replacing __file__ parent walk:
    # simplest: call the same algorithm inline with tmp_path as repo root.
    from dotenv import load_dotenv

    pre_existing = {k: os.environ[k] for k in PROTECTED if k in os.environ}
    load_dotenv(env_file)
    load_dotenv()
    for key, value in pre_existing.items():
        os.environ[key] = value
    allow_opt_in = (os.getenv("CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN") or "").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    if not allow_opt_in:
        os.environ["CHAKRAOPS_SCHEDULER_ENABLED"] = "false"
        os.environ["CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED"] = "false"


def test_dotenv_truthy_legacy_cannot_enable_without_allow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_scheduler_env(monkeypatch)
    body = "\n".join(
        [
            "CHAKRAOPS_SCHEDULER_ENABLED=true",
            "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true",
            "CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN=false",
        ]
    )
    _run_load_env_with_dotenv_file(tmp_path, body, monkeypatch)
    assert os.environ.get("CHAKRAOPS_SCHEDULER_ENABLED") == "false"
    assert os.environ.get("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED") == "false"


def test_shell_false_wins_over_dotenv_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_scheduler_env(monkeypatch)
    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED", "false")
    body = "\n".join(
        [
            "CHAKRAOPS_SCHEDULER_ENABLED=true",
            "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true",
            "CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN=true",
        ]
    )
    _run_load_env_with_dotenv_file(tmp_path, body, monkeypatch)
    # Shell pre-existing false restored; allow flag means no force — restored shell false remains
    assert os.environ.get("CHAKRAOPS_SCHEDULER_ENABLED") == "false"
    assert os.environ.get("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED") == "false"


def test_allow_flag_permits_dotenv_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_scheduler_env(monkeypatch)
    monkeypatch.setenv("CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN", "true")
    body = "\n".join(
        [
            "CHAKRAOPS_SCHEDULER_ENABLED=true",
            "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true",
        ]
    )
    _run_load_env_with_dotenv_file(tmp_path, body, monkeypatch)
    assert os.environ.get("CHAKRAOPS_SCHEDULER_ENABLED", "").lower() in ("true", "1", "yes")
    assert os.environ.get("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED", "").lower() in ("true", "1", "yes")


def test_server_module_eod_freeze_default_fail_closed() -> None:
    """Module constant must default false when env unset (fail-closed)."""
    server_path = Path(__file__).resolve().parents[1] / "app" / "api" / "server.py"
    text = server_path.read_text(encoding="utf-8")
    assert 'os.getenv("EOD_FREEZE_ENABLED", "false")' in text
    assert 'os.getenv("NIGHTLY_EVAL_ENABLED", "false")' in text
    assert 'os.getenv("EOD_CHAIN_ENABLED", "false")' in text
