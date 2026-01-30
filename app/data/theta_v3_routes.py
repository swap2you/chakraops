# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Shared Theta v3 routing helpers (no trading logic).

Centralizes:
- Base URL from config.yaml (with THETA_REST_URL env override)
- Stock / option / index URL builders
- Optional Authorization header from THETA_API_KEY

All URLs are built from the centralized config. No hardcoded URLs.
"""

from __future__ import annotations

import os
from typing import Dict

from app.core.settings import get_theta_base_url


def _get_base() -> str:
    """Get base URL from centralized config (supports env override)."""
    return get_theta_base_url().rstrip("/")


# Lazy-loaded base URL (compatible with existing code that imports _BASE)
_BASE: str = ""


def _ensure_base() -> str:
    """Ensure _BASE is initialized."""
    global _BASE
    if not _BASE:
        _BASE = _get_base()
    return _BASE


def base_url() -> str:
    """Return the Theta v3 base URL from centralized config."""
    return _ensure_base()


def stock_url(path: str) -> str:
    """Build full URL for stock namespace."""
    return f"{_ensure_base()}/stock{path}"


def option_url(path: str) -> str:
    """Build full URL for option namespace."""
    return f"{_ensure_base()}/option{path}"


def index_url(path: str) -> str:
    """Build full URL for index namespace."""
    return f"{_ensure_base()}/index{path}"


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

