# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R62: production requires PostgreSQL; local may use SQLite."""

from __future__ import annotations

import pytest

from app.core.data_platform.db import is_production_env, reset_engine_cache, resolve_database_url


@pytest.fixture(autouse=True)
def _reset():
    reset_engine_cache()
    yield
    reset_engine_cache()


def test_local_defaults_sqlite(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_PRODUCTION", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEPLOY_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert is_production_env() is False
    assert resolve_database_url().startswith("sqlite:///")


def test_production_requires_postgres_url(monkeypatch):
    monkeypatch.setenv("CHAKRAOPS_PRODUCTION", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        resolve_database_url()


def test_production_rejects_sqlite(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/x.db")
    with pytest.raises(RuntimeError, match="SQLite is not allowed"):
        resolve_database_url()


def test_production_accepts_postgres(monkeypatch):
    monkeypatch.setenv("DEPLOY_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/chakraops")
    url = resolve_database_url()
    assert url.startswith("postgresql+psycopg://")
