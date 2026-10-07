# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-030/031/101 persistence honesty + atomic JSON writers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.data_platform.db import reset_engine_cache, runtime_persistence_inventory
from app.core.io.atomic import atomic_write_json


@pytest.fixture(autouse=True)
def _reset_db():
    reset_engine_cache()
    yield
    reset_engine_cache()


def test_r70_def030_runtime_inventory_denies_postgres_portfolio_sot(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_PRODUCTION", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEPLOY_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    inv = runtime_persistence_inventory()
    assert inv["postgres_is_portfolio_sot"] is False
    assert inv["platform_database"]["is_live_portfolio_sot"] is False
    assert inv["platform_database"]["is_live_broker_snapshot_sot"] is False
    names = {s["name"] for s in inv["critical_runtime_stores"]}
    assert "broker_snapshots" in names
    assert "holdings_manual" in names
    assert inv["migration_status"] == "DEFERRED_XL"


def test_r70_def030_production_gate_still_requires_postgres(monkeypatch):
    monkeypatch.setenv("CHAKRAOPS_PRODUCTION", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/chakraops")
    inv = runtime_persistence_inventory()
    assert inv["platform_database"]["url_kind"] == "postgres"
    # Gate OK ≠ portfolio SoT
    assert inv["postgres_is_portfolio_sot"] is False


def test_r70_def031_store_authority_matrix_documented():
    """Objective DEFER evidence: inventory lists multiple authorities, no collapse yet."""
    inv = runtime_persistence_inventory()
    authorities = {s["authority"] for s in inv["critical_runtime_stores"]}
    assert len(authorities) >= 3
    assert inv["migration_status"] == "DEFERRED_XL"


def test_r70_def101_atomic_write_json_dict_and_list(tmp_path: Path):
    dpath = tmp_path / "state.json"
    atomic_write_json(dpath, {"a": 1}, indent=2)
    assert json.loads(dpath.read_text(encoding="utf-8")) == {"a": 1}
    assert not dpath.with_suffix(".json.tmp").exists()

    lpath = tmp_path / "positions.json"
    atomic_write_json(lpath, [{"id": "p1"}], indent=2)
    assert json.loads(lpath.read_text(encoding="utf-8")) == [{"id": "p1"}]


def test_r70_def101_monitor_and_ledger_use_atomic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.core.monitor.advisory_worker_r54 import AdvisoryMonitorWorker
    from app.core.positions.position_ledger import save_open_positions, load_open_positions

    w = AdvisoryMonitorWorker()
    w.last_run_at = "2026-08-11T00:00:00Z"
    w.running = False
    w._persist_state()
    state_path = w._state_path()
    assert state_path.exists()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["manual_only"] is True
    assert payload["trade_execution"] is False

    ledger = tmp_path / "open_positions.json"
    save_open_positions([{"position_id": "x", "status": "OPEN", "symbol": "SPY"}], ledger)
    assert load_open_positions(ledger)[0]["symbol"] == "SPY"
