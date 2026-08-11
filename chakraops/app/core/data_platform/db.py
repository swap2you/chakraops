# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R51 data platform engine — PostgreSQL when DATABASE_URL set; else SQLite.

R70 honesty (DEF-030): Production still requires a PostgreSQL DATABASE_URL for the
SQLAlchemy *platform* engine gate. Critical LIVE portfolio/broker stores remain
SQLite/JSON until an explicit migration — see runtime_persistence_inventory().
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

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
    """True when running in production deploy mode (Postgres mandatory for platform URL)."""
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


def runtime_persistence_inventory() -> Dict[str, Any]:
    """Honest SoT map: platform URL gate vs stores that still write SQLite/JSON.

    R70-DEF-030: Do not claim Postgres is LIVE portfolio/broker SoT until migrated.
    """
    try:
        platform_url = resolve_database_url()
    except Exception as exc:  # noqa: BLE001 — surface gate errors honestly
        platform_url = f"UNRESOLVED:{type(exc).__name__}"
    platform_kind = "postgres" if str(platform_url).startswith("postgresql") else "sqlite"
    if str(platform_url).startswith("UNRESOLVED:"):
        platform_kind = "unresolved"
    return {
        "schema": "runtime_persistence_inventory_r70",
        "platform_database": {
            "engine": "sqlalchemy",
            "url_kind": platform_kind,
            "role": "production_url_gate_and_scaffolded_models",
            "is_live_portfolio_sot": False,
            "is_live_broker_snapshot_sot": False,
            "note": (
                "R62 production gate requires PostgreSQL DATABASE_URL. "
                "Critical broker/portfolio paths are not yet migrated onto this engine."
            ),
        },
        "critical_runtime_stores": [
            {
                "name": "broker_snapshots",
                "backend": "sqlite+json",
                "module": "app.core.broker.snapshot_store",
                "authority": "LIVE last-good broker read",
            },
            {
                "name": "holdings_manual",
                "backend": "sqlite",
                "module": "app.core.accounts.holdings_db",
                "authority": "Recovery/manual entry — not LIVE",
            },
            {
                "name": "positions_unified",
                "backend": "sqlite",
                "module": "app.core.portfolio.positions_unified_store_r279",
                "authority": "Derived mirror / repair surface",
            },
            {
                "name": "ticket_queue",
                "backend": "sqlite",
                "module": "app.core.ops.ticket_queue_store_r42",
                "authority": "Manual ticket queue",
            },
            {
                "name": "decision_artifacts",
                "backend": "json",
                "module": "app.core.eval.evaluation_store_v2",
                "authority": "LIVE decision_latest / eval snapshot",
            },
        ],
        "postgres_is_portfolio_sot": False,
        "migration_status": "DEFERRED_XL",
        "manual_only": True,
        "trade_execution": False,
    }


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
