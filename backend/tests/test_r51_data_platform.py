# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R51 data platform foundation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.data_platform.db import (
    get_engine,
    reset_engine_cache,
    resolve_database_url,
    session_scope,
)
from app.core.data_platform.models_sql import Base, BrokerSnapshotRow, create_all
from app.core.data_platform.migrate_sqlite_inventory import inventory


@pytest.fixture(autouse=True)
def _reset_engine():
    reset_engine_cache()
    yield
    reset_engine_cache()


def test_resolve_database_url_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = resolve_database_url()
    assert url.startswith("sqlite:///")
    assert "chakraops_platform.db" in url


def test_resolve_database_url_accepts_postgres(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@localhost:5432/chakraops",
    )
    url = resolve_database_url()
    assert url.startswith("postgresql+psycopg://")


def test_resolve_database_url_normalizes_postgresql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/chakraops")
    url = resolve_database_url()
    assert url.startswith("postgresql+psycopg://")


def test_resolve_database_url_fail_closed_invalid_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@localhost/db")
    with pytest.raises(ValueError, match="scheme not allowed"):
        resolve_database_url()


def test_create_tables_and_roundtrip_snapshot(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "platform_test.db"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    reset_engine_cache()

    engine = get_engine(url=url, force_new=True)
    create_all(engine)

    payload = {"equity": 150000.0, "source": "test", "positions": [{"symbol": "NVDA", "qty": 10}]}

    session = session_scope(url=url)
    try:
        row = BrokerSnapshotRow(
            account_alias="individual",
            fetched_at="2026-08-10T00:00:00Z",
            stale=False,
            payload=payload,
        )
        session.add(row)
        session.commit()
        row_id = row.id
    finally:
        session.close()

    session = session_scope(url=url)
    try:
        loaded = session.get(BrokerSnapshotRow, row_id)
        assert loaded is not None
        assert loaded.account_alias == "individual"
        assert loaded.payload["equity"] == 150000.0
        assert loaded.payload["positions"][0]["symbol"] == "NVDA"
        assert loaded.stale is False
    finally:
        session.close()


def test_create_tables_memory_sqlite():
    url = "sqlite:///:memory:"
    engine = get_engine(url=url, force_new=True)
    create_all(engine)
    names = set(Base.metadata.tables.keys())
    for expected in (
        "broker_accounts",
        "broker_snapshots",
        "positions_normalized",
        "journal_fills",
        "tickets",
        "universe_lifecycle",
        "decisions",
        "alerts",
        "job_runs",
        "audit_events",
    ):
        assert expected in names


def test_inventory_read_only(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "journal.db").write_bytes(b"")
    out = tmp_path / "out"
    out.mkdir()
    (out / "decision_latest.json").write_text("{}", encoding="utf-8")

    report = inventory(roots=[data, out])
    assert report["mode"] == "read_only_inventory"
    assert report["store_count"] >= 1
    paths = [s["path"] for s in report["stores"] if s.get("exists")]
    assert any(p.endswith("decision_latest.json") for p in paths)
