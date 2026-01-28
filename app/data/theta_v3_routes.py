# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Shared Theta v3 routing helpers (no trading logic).

Centralizes:
- Base URL (THETA_REST_URL, default http://127.0.0.1:25503/v3)
- Stock / option / index URL builders
- Optional Authorization header from THETA_API_KEY
"""

from __future__ import annotations

import os
from typing import Dict


_BASE = os.getenv("THETA_REST_URL", "http://127.0.0.1:25503/v3").rstrip("/")


def base_url() -> str:
    return _BASE


def stock_url(path: str) -> str:
    """Build full URL for stock namespace."""
    return f"{_BASE}/stock{path}"


def option_url(path: str) -> str:
    """Build full URL for option namespace."""
    return f"{_BASE}/option{path}"


def index_url(path: str) -> str:
    """Build full URL for index namespace."""
    return f"{_BASE}/index{path}"


def build_headers() -> Dict[str, str]:
    """Optional auth headers (masked in logs by callers).

    Currently supports THETA_API_KEY -> Authorization: Bearer <key>.
    """
    headers: Dict[str, str] = {}
    api_key = os.getenv("THETA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


__all__ = ["base_url", "stock_url", "option_url", "index_url", "build_headers"]

