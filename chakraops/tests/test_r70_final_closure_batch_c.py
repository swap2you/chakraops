# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure Batch C — eval authority seal + ledger tallies."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_canonical_output_alias_is_detected(tmp_path: Path) -> None:
    from app.core.eval.evaluation_store_v2 import DECISION_STORE_PATH, is_canonical_output_dir

    alias = tmp_path / "canonical-out-alias"
    try:
        alias.symlink_to(DECISION_STORE_PATH.parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    assert is_canonical_output_dir(alias) is True


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

    out = ec.run_universe_evaluation_exclusive(["A", "B", "C"], trigger="api")
    assert out.get("started") is True
    run = saved["run"]
    assert run.holds == 1
    assert run.blocks == 1
    assert run.alerts and run.alerts[0].get("type") == "PROVENANCE"
    assert service._canonical_live_universe_write_is_authorized() is False
