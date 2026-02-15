# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Symbol diagnostics service — shared by /api/view/symbol-diagnostics and /api/ui/symbol-diagnostics."""

from __future__ import annotations

from typing import Any, Dict, Optional


def get_symbol_diagnostics(symbol: str, mode: Optional[str] = "csp") -> Dict[str, Any]:
    """Fetch full symbol diagnostics. Wraps server's api_view_symbol_diagnostics (lazy import to avoid cycle)."""
    from app.api.server import api_view_symbol_diagnostics
    return api_view_symbol_diagnostics(symbol=symbol, mode=mode)
