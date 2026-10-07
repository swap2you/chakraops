# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Dedicated local dev ports for ChakraOps (avoid conflicts with Docker and other apps).

Single source of truth for the Python layer. PowerShell (scripts/chakraops_ports.ps1)
and Vite (frontend/vite.config.*) implement the same resolution rules:

- Unset/empty env var -> default.
- Env var set -> must be an integer in [1, 65535], else fail clearly.
- Backend and frontend ports must differ.
"""

from __future__ import annotations

import os

MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_BACKEND_PORT = 18800
DEFAULT_FRONTEND_PORT = 18873

BACKEND_PORT_ENV = "CHAKRAOPS_BACKEND_PORT"
FRONTEND_PORT_ENV = "CHAKRAOPS_FRONTEND_PORT"


def resolve_port(env_name: str, default: int) -> int:
    """Resolve a port from an env var with validation.

    Falls back to ``default`` when the variable is unset or empty. Raises
    ``ValueError`` for non-numeric or out-of-range values (fail-fast).
    """
    raw = os.getenv(env_name)
    if raw is None or raw.strip() == "":
        return default
    raw = raw.strip()
    if not raw.isdigit():
        raise ValueError(
            f"{env_name}={raw!r} is not a valid port (must be an integer {MIN_PORT}-{MAX_PORT})"
        )
    value = int(raw)
    if value < MIN_PORT or value > MAX_PORT:
        raise ValueError(f"{env_name}={value} is out of range ({MIN_PORT}-{MAX_PORT})")
    return value


def resolve_ports() -> tuple[int, int]:
    """Resolve (backend, frontend) ports and reject equal values."""
    backend = resolve_port(BACKEND_PORT_ENV, DEFAULT_BACKEND_PORT)
    frontend = resolve_port(FRONTEND_PORT_ENV, DEFAULT_FRONTEND_PORT)
    if backend == frontend:
        raise ValueError(
            f"Backend and frontend ports must differ (both={backend}); "
            f"set distinct {BACKEND_PORT_ENV}/{FRONTEND_PORT_ENV}"
        )
    return backend, frontend


BACKEND_PORT, FRONTEND_PORT = resolve_ports()


def backend_base_url(host: str = "127.0.0.1") -> str:
    return f"http://{host}:{BACKEND_PORT}"


def frontend_origin_default() -> str:
    return f"http://127.0.0.1:{FRONTEND_PORT}"
