# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Evaluation pipeline config: quote window, staleness.

Config key: EVALUATION_QUOTE_WINDOW_MINUTES — window (minutes) within which
quote data is considered current for evaluation; default 30 (not intraday).
Override via env: EVALUATION_QUOTE_WINDOW_MINUTES.
"""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Default 30 minutes; used for reporting / staleness context (trading-day staleness is separate)
EVALUATION_QUOTE_WINDOW_MINUTES: int = _int_env("EVALUATION_QUOTE_WINDOW_MINUTES", 30)

__all__ = ["EVALUATION_QUOTE_WINDOW_MINUTES"]
