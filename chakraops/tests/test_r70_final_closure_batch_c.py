# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure Batch C — eval authority seal + ledger tallies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def test_offline_eval_proof_refuses_canonical_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.offline_eval_proof as proof
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH

    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    canonical_file = DECISION_STORE_PATH
    before = canonical_file.read_bytes() if canonical_file.exists() else None
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline_eval_proof.py",
            "--fixture",
            str(fixture),
            "--output-dir",
            str(canonical_file.parent),
        ],
    )

    assert proof.main() == 2
    after = canonical_file.read_bytes() if canonical_file.exists() else None
    assert after == before


def _link_canonical_alias(alias: Path, target: Path) -> str:
    """Create a directory alias. Prefer symlink; fall back to a Windows junction."""
    try:
        alias.symlink_to(target, target_is_directory=True)
        return "symlink"
    except OSError:
        if os.name != "nt":
            raise
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise OSError(completed.stderr or completed.stdout or "mklink /J failed")
        return "junction"


def test_canonical_output_alias_is_detected(tmp_path: Path) -> None:
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH, is_canonical_output_dir

    alias = tmp_path / "canonical-out-alias"
    try:
        _link_canonical_alias(alias, DECISION_STORE_PATH.parent)
    except OSError as exc:
        pytest.skip(f"symlink/junction unavailable: {exc}")
    try:
        assert is_canonical_output_dir(alias) is True
    finally:
        if alias.exists() or alias.is_symlink():
            try:
                alias.unlink()
            except OSError:
                alias.rmdir()


def test_canonical_output_relative_path_alias_is_detected() -> None:
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH, is_canonical_output_dir

    relative_alias = DECISION_STORE_PATH.parent / "r70_1_alias_probe" / ".."
    assert is_canonical_output_dir(relative_alias) is True


def test_offline_eval_proof_refuses_relative_canonical_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.offline_eval_proof as proof
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH

    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    canonical_file = DECISION_STORE_PATH
    before = canonical_file.read_bytes() if canonical_file.exists() else None
    relative_alias = canonical_file.parent / "r70_1_alias_probe" / ".."
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline_eval_proof.py",
            "--fixture",
            str(fixture),
            "--output-dir",
            str(relative_alias),
        ],
    )

    assert proof.main() == 2
    after = canonical_file.read_bytes() if canonical_file.exists() else None
    assert after == before


def test_frontend_test_scripts_skip_rollup_native() -> None:
    repo = Path(__file__).resolve().parents[2]
    pkg = json.loads((repo / "frontend" / "package.json").read_text(encoding="utf-8"))
    for script_name in ("dev", "build", "preview", "test", "test:watch", "live:check"):
        assert "ROLLUP_SKIP_NODEJS_NATIVE=1" in pkg["scripts"][script_name], script_name


def test_run_and_save_refuses_canonical_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_and_save as ras

    args = SimpleNamespace(all=False, symbols="SPY", limit=1)
    # Point repo-style canonical
    with patch.object(ras, "_REPO_ROOT", tmp_path):
        (tmp_path / "out").mkdir()
        code, path = ras.run_one(args, tmp_path / "out")
    assert code == 2
    assert path is None


def test_run_and_save_seals_set_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_and_save as ras

    harness = tmp_path / "harness"
    harness.mkdir()

    class _Art:
        def to_dict(self):
            return {"metadata": {}, "symbols": []}

    def _fake_eval(symbols, mode="LIVE", output_dir=None):
        assert mode == "PAPER"
        assert output_dir is not None
        assert "harness" in str(output_dir)
        return _Art()

    monkeypatch.setattr(
        "app.core.eval.evaluation_service_v2.evaluate_universe",
        _fake_eval,
    )
    args = SimpleNamespace(all=False, symbols="SPY", limit=1)
    with patch.object(ras, "_REPO_ROOT", tmp_path):
        code, path = ras.run_one(args, harness)
    assert code == 0
    assert path is not None and path.exists()
    raw = path.read_text(encoding="utf-8")
    assert "SECONDARY_HARNESS" in raw or "secondary_harness" in raw


def test_coordinator_tallies_holds_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import eval_coordinator as ec
    from app.core.eval import evaluation_service_v2 as service

    syms = [
        SimpleNamespace(symbol="A", verdict="HOLD", primary_reason="x", score=10),
        SimpleNamespace(symbol="B", verdict="BLOCKED", primary_reason="y", score=0),
        SimpleNamespace(symbol="C", verdict="ELIGIBLE", primary_reason="z", score=80),
    ]
    artifact = SimpleNamespace(
        symbols=syms,
        metadata={"universe_size": 3, "evaluated_count_stage1": 3, "eligible_count": 1, "market_phase": "OPEN"},
    )

    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "eval_test_1"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-12T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "eval_test_1"

    saved = {}

    def _save(run):
        saved["run"] = run

    monkeypatch.setattr(
        "app.market.market_hours.get_market_phase",
        lambda: "OPEN",
    )
    def _fake_eval(symbols, mode="LIVE"):
        assert service._canonical_live_universe_write_is_authorized() is True
        return artifact

    monkeypatch.setattr("app.core.eval.evaluation_service_v2.evaluate_universe", _fake_eval)
    monkeypatch.setattr("app.core.eval.evaluation_store.save_run", _save)
    monkeypatch.setattr("app.core.eval.evaluation_store.update_latest_pointer", lambda *a, **k: None)
    alert_calls: list = []
    monkeypatch.setattr(
        "app.core.alerts.alert_engine.process_run_completed",
        lambda run: alert_calls.append(run),
    )
    monkeypatch.setattr(
        "app.core.alerts.options_lifecycle_notifications.emit_options_lifecycle_notifications_from_run",
        lambda run: None,
    )
    monkeypatch.setattr(
        "app.core.universe_v2.builder.build_universe_v2_snapshot",
        lambda: None,
    )

    out = ec.run_universe_evaluation_exclusive(["A", "B", "C"], trigger="api")
    assert out.get("started") is True
    run = saved["run"]
    assert run.holds == 1
    assert run.blocks == 1
    assert run.alerts and run.alerts[0].get("type") == "PROVENANCE"
    assert service._canonical_live_universe_write_is_authorized() is False
    assert len(alert_calls) == 1
    assert alert_calls[0] is run


def test_coordinator_scope_resets_on_evaluation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import eval_coordinator as ec
    from app.core.eval import evaluation_service_v2 as service

    monkeypatch.setattr(ec, "try_begin_universe_evaluation", lambda trigger: (True, "eval_fail_1"))
    monkeypatch.setattr(ec, "end_universe_evaluation", lambda *_a, **_k: None)
    with ec._COORD_META_LOCK:
        ec._ACTIVE_STARTED_AT = "2026-08-12T12:00:00+00:00"
        ec._ACTIVE_TRIGGER = "api"
        ec._ACTIVE_RUN_ID = "eval_fail_1"

    def _boom(symbols, mode="LIVE"):
        assert service._canonical_live_universe_write_is_authorized() is True
        raise RuntimeError("eval boom")

    monkeypatch.setattr("app.market.market_hours.get_market_phase", lambda: "OPEN")
    monkeypatch.setattr("app.core.eval.evaluation_service_v2.evaluate_universe", _boom)
    monkeypatch.setattr("app.core.eval.evaluation_store.save_failed_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="eval boom"):
        ec.run_universe_evaluation_exclusive(["A"], trigger="api")
    assert service._canonical_live_universe_write_is_authorized() is False
