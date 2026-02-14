# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.8: Evaluation Budget — max symbols, wall time, request count.

Hard cap target per cycle. Used by evaluation runner to trim symbols,
stop on time, and emit health warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.config.eval_config import (
    EVAL_MAX_REQUESTS_ESTIMATE,
    EVAL_MAX_SYMBOLS_PER_CYCLE,
    EVAL_MAX_WALL_TIME_SEC,
)


@dataclass
class EvaluationBudget:
    """
    Budget for a single evaluation cycle.
    Tracks symbols_processed, requests_estimated, batches_processed.
    """
    max_wall_time_sec: int
    max_symbols: int
    max_requests_estimate: int
    started_at: datetime
    symbols_processed: int = 0
    requests_estimated: int = 0
    batches_processed: int = 0

    @classmethod
    def from_config(
        cls,
        max_wall_time_sec: int | None = None,
        max_symbols: int | None = None,
        max_requests_estimate: int | None = None,
        started_at: datetime | None = None,
    ) -> "EvaluationBudget":
        return cls(
            max_wall_time_sec=max_wall_time_sec or EVAL_MAX_WALL_TIME_SEC,
            max_symbols=max_symbols or EVAL_MAX_SYMBOLS_PER_CYCLE,
            max_requests_estimate=max_requests_estimate or EVAL_MAX_REQUESTS_ESTIMATE,
            started_at=started_at or datetime.now(timezone.utc),
        )

    def can_continue(self, now: datetime | None = None) -> bool:
        """True if budget allows more work (wall time not exceeded)."""
        n = now or datetime.now(timezone.utc)
        elapsed = (n - self.started_at).total_seconds()
        return elapsed < self.max_wall_time_sec

    def should_stop_for_time(self, now: datetime | None = None) -> bool:
        """True if wall time cap reached — stop processing."""
        return not self.can_continue(now)

    def trim_symbols(self, symbols: List[str]) -> List[str]:
        """Enforce max_symbols; return trimmed list preserving order."""
        if not symbols:
            return []
        return symbols[: self.max_symbols]

    def record_batch(
        self,
        symbols_count: int,
        requests_estimate: int | None = None,
        endpoints_used: List[str] | None = None,
    ) -> None:
        """
        Record a processed batch.
        If endpoints_used provided, compute requests_estimate via request_cost_model.
        Otherwise use requests_estimate if given.
        """
        self.symbols_processed += symbols_count
        if endpoints_used is not None:
            from app.core.eval.request_cost_model import estimate_requests_for_symbols
            self.requests_estimated += estimate_requests_for_symbols(
                [""] * symbols_count,
                endpoints_used=endpoints_used,
            )
        elif requests_estimate is not None:
            self.requests_estimated += requests_estimate
        self.batches_processed += 1

    def budget_status(self) -> Dict[str, Any]:
        """Return status dict for logging/health."""
        now = datetime.now(timezone.utc)
        elapsed_sec = (now - self.started_at).total_seconds()
        return {
            "max_wall_time_sec": self.max_wall_time_sec,
            "max_symbols": self.max_symbols,
            "elapsed_sec": round(elapsed_sec, 1),
            "symbols_processed": self.symbols_processed,
            "requests_estimated": self.requests_estimated,
            "batches_processed": self.batches_processed,
            "time_exceeded": self.should_stop_for_time(now),
        }
