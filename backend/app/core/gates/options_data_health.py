# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options data health gate (Phase 8).

If valid_symbols == 0 -> BLOCK with clear reason.
If valid_symbols > 0 -> allow pipeline to continue for those symbols only.
Do NOT let one bad symbol poison the entire run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


REASON_NO_SYMBOLS_WITH_OPTIONS = "NO_SYMBOLS_WITH_OPTIONS"


@dataclass(frozen=True)
class OptionsDataHealthResult:
    """Result of options data health check."""

    allowed: bool
    valid_symbols_count: int
    excluded_count: int
    reasons: List[str]


def evaluate_options_data_health(
    symbols_with_options: List[str],
    symbols_without_options: Dict[str, str],
) -> OptionsDataHealthResult:
    """Evaluate whether we have at least one symbol with valid options data.

    Args:
        symbols_with_options: List of symbols that had valid options (expirations + contracts).
        symbols_without_options: Dict symbol -> reason for symbols without usable options.

    Returns:
        OptionsDataHealthResult. allowed=False only when valid_symbols_count == 0.
    """
    valid_count = len(symbols_with_options)
    excluded_count = len(symbols_without_options)
    reasons: List[str] = []

    if valid_count == 0:
        reasons.append(REASON_NO_SYMBOLS_WITH_OPTIONS)
        if symbols_without_options:
            # Summarize top reasons
            reason_counts: Dict[str, int] = {}
            for r in symbols_without_options.values():
                reason_counts[r] = reason_counts.get(r, 0) + 1
            top = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            for r, c in top:
                reasons.append(f"{r}: {c} symbol(s)")
        return OptionsDataHealthResult(
            allowed=False,
            valid_symbols_count=0,
            excluded_count=excluded_count,
            reasons=reasons,
        )

    return OptionsDataHealthResult(
        allowed=True,
        valid_symbols_count=valid_count,
        excluded_count=excluded_count,
        reasons=[],
    )


__all__ = ["evaluate_options_data_health", "OptionsDataHealthResult", "REASON_NO_SYMBOLS_WITH_OPTIONS"]
