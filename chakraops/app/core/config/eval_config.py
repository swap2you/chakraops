# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Evaluation pipeline config: quote window, staleness, Phase 8.8 budget/batch/cache.

Config key: EVALUATION_QUOTE_WINDOW_MINUTES — window (minutes) within which
quote data is considered current for evaluation; default 30 (not intraday).
Override via env: EVALUATION_QUOTE_WINDOW_MINUTES.

Phase 8.8: EVAL_MAX_WALL_TIME_SEC, EVAL_MAX_SYMBOLS_PER_CYCLE, EVAL_BATCH_SIZE,
EVAL_MAX_CONCURRENCY, EVAL_MAX_REQUESTS_ESTIMATE, CACHE_DIR, CACHE_ENABLED.
"""

from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name, "").lower().strip()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return default


# Default 30 minutes; used for reporting / staleness context (trading-day staleness is separate)
EVALUATION_QUOTE_WINDOW_MINUTES: int = _int_env("EVALUATION_QUOTE_WINDOW_MINUTES", 30)

# Phase 8.8: Evaluation budget and batch
EVAL_MAX_WALL_TIME_SEC: int = _int_env("EVAL_MAX_WALL_TIME_SEC", 240)
EVAL_MAX_SYMBOLS_PER_CYCLE: int = _int_env("EVAL_MAX_SYMBOLS_PER_CYCLE", 25)
EVAL_BATCH_SIZE: int = _int_env("EVAL_BATCH_SIZE", 10)
EVAL_MAX_CONCURRENCY: int = _int_env("EVAL_MAX_CONCURRENCY", 10)
EVAL_MAX_REQUESTS_ESTIMATE: int = _int_env("EVAL_MAX_REQUESTS_ESTIMATE", 1000)

# Phase 8.8: ORATS cache (file-based, TTL)
def _cache_dir() -> Path:
    raw = os.getenv("CACHE_DIR", "")
    if raw and raw.strip():
        return Path(raw.strip())
    repo = Path(__file__).resolve().parents[3]
    return repo / "artifacts" / "cache" / "orats"


CACHE_DIR: Path = _cache_dir()
CACHE_ENABLED: bool = _bool_env("CACHE_ENABLED", True)
CACHE_MAX_AGE_DAYS: int = _int_env("CACHE_MAX_AGE_DAYS", 7)
CACHE_MAX_FILES: int = _int_env("CACHE_MAX_FILES", 20000)

__all__ = [
    "EVALUATION_QUOTE_WINDOW_MINUTES",
    "EVAL_MAX_WALL_TIME_SEC",
    "EVAL_MAX_SYMBOLS_PER_CYCLE",
    "EVAL_BATCH_SIZE",
    "EVAL_MAX_CONCURRENCY",
    "EVAL_MAX_REQUESTS_ESTIMATE",
    "CACHE_DIR",
    "CACHE_ENABLED",
    "CACHE_MAX_AGE_DAYS",
    "CACHE_MAX_FILES",
]
