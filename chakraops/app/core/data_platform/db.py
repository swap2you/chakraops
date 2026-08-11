# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R51 data platform engine — PostgreSQL when DATABASE_URL set; else SQLite."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_ENGINE: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _default_sqlite_url() -> str:
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        base = Path(data_dir).resolve()
    else:
        base = Path(__file__).resolve().parents[3] / "data"
    base.mkdir(parents=True, exist_ok=True)
    path = (base / "chakraops_platform.db").as_posix()
    return f"sqlite:///{path}"


def is_production_env() -> bool:
    """True when running in production deploy mode (Postgres mandatory)."""
    flags = (
        os.environ.get("CHAKRAOPS_PRODUCTION"),
        os.environ.get("DEPLOY_ENV"),
        os.environ.get("APP_ENV"),
    )
    for f in flags:
        if (f or "").strip().lower() in {"1", "true", "yes", "production", "prod"}:
            return True
    return False


def resolve_database_url(url: Optional[str] = None) -> str:
    raw = (url if url is not None else os.environ.get("DATABASE_URL") or "").strip()
    if is_production_env():
        if not raw:
            raise RuntimeError(
                "Production requires DATABASE_URL with PostgreSQL "
                "(CHAKRAOPS_PRODUCTION/APP_ENV/DEPLOY_ENV=production). SQLite fallback disabled."
            )
        lower = raw.lower()
        if not (
            lower.startswith("postgresql://")
            or lower.startswith("postgresql+psycopg://")
            or lower.startswith("postgresql+psycopg2://")
        ):
            raise RuntimeError(
                "Production DATABASE_URL must be PostgreSQL; SQLite is not allowed in production."
            )
        if lower.startswith("postgresql://") and "+psycopg" not in lower:
            return "postgresql+psycopg://" + raw[len("postgresql://") :]
        return raw
    if not raw:
        return _default_sqlite_url()
    lower = raw.lower()
    allowed_prefixes = (
        "sqlite://",
        "postgresql://",
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
    )
    if not any(lower.startswith(p) for p in allowed_prefixes):
        raise ValueError(
            f"DATABASE_URL scheme not allowed (sqlite / postgresql only): {raw.split(':', 1)[0]}"
        )
    if lower.startswith("postgresql://") and "+psycopg" not in lower:
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw


def get_engine(*, url: Optional[str] = None, force_new: bool = False) -> Engine:
    global _ENGINE, _SessionLocal
    if _ENGINE is not None and not force_new and url is None:
        return _ENGINE
    resolved = resolve_database_url(url)
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    engine = create_engine(resolved, future=True, connect_args=connect_args)
    if (url is None or not force_new) and not force_new:
        _ENGINE = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    elif force_new and url is not None:
        # Ephemeral engines for tests — do not clobber global unless url is default path
        return engine
    if url is None:
        _ENGINE = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def session_scope(*, url: Optional[str] = None) -> Session:
    """Return a Session bound to url (or default engine). Caller must close()."""
    if url:
        engine = get_engine(url=url, force_new=True)
        return Session(engine)
    return get_session()


def reset_engine_cache() -> None:
    global _ENGINE, _SessionLocal
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SessionLocal = None
