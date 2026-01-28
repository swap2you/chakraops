# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options-layer config: DTE, delta, spread, OI, volume, ROC (Phase 5).

Env overrides: CSP_MIN_DTE, CSP_MAX_DTE, CSP_TARGET_DELTA_LOW/HIGH (or DELTA_MIN/MAX),
CC_*, MAX_SPREAD_PCT, MIN_OI, MIN_VOLUME, MIN_ROC.
"""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# CSP
CSP_MIN_DTE: int = _int_env("CSP_MIN_DTE", 30)
CSP_MAX_DTE: int = _int_env("CSP_MAX_DTE", 45)
CSP_TARGET_DELTA_LOW: float = _float_env("CSP_TARGET_DELTA_LOW", 0.25)
CSP_TARGET_DELTA_HIGH: float = _float_env("CSP_TARGET_DELTA_HIGH", 0.35)
# Allow CSP_DELTA_MIN/MAX as aliases (puts: negative; config is absolute 0.15–0.30)
CSP_DELTA_MIN: float = _float_env("CSP_DELTA_MIN", CSP_TARGET_DELTA_LOW)
CSP_DELTA_MAX: float = _float_env("CSP_DELTA_MAX", CSP_TARGET_DELTA_HIGH)

# CC
CC_MIN_DTE: int = _int_env("CC_MIN_DTE", 30)
CC_MAX_DTE: int = _int_env("CC_MAX_DTE", 45)
CC_TARGET_DELTA_LOW: float = _float_env("CC_TARGET_DELTA_LOW", 0.15)
CC_TARGET_DELTA_HIGH: float = _float_env("CC_TARGET_DELTA_HIGH", 0.35)
CC_DELTA_MIN: float = _float_env("CC_DELTA_MIN", CC_TARGET_DELTA_LOW)
CC_DELTA_MAX: float = _float_env("CC_DELTA_MAX", CC_TARGET_DELTA_HIGH)

# Liquidity / quality
MAX_SPREAD_PCT: float = _float_env("MAX_SPREAD_PCT", 20.0)
MIN_OI: int = _int_env("MIN_OI", 0)
MIN_VOLUME: int = _int_env("MIN_VOLUME", 0)
MIN_ROC: float = _float_env("MIN_ROC", 0.005)

__all__ = [
    "CSP_MIN_DTE",
    "CSP_MAX_DTE",
    "CSP_TARGET_DELTA_LOW",
    "CSP_TARGET_DELTA_HIGH",
    "CSP_DELTA_MIN",
    "CSP_DELTA_MAX",
    "CC_MIN_DTE",
    "CC_MAX_DTE",
    "CC_TARGET_DELTA_LOW",
    "CC_TARGET_DELTA_HIGH",
    "CC_DELTA_MIN",
    "CC_DELTA_MAX",
    "MAX_SPREAD_PCT",
    "MIN_OI",
    "MIN_VOLUME",
    "MIN_ROC",
]
