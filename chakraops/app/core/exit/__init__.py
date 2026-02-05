# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Exit and stop logic: formal stop-loss, profit-take, time and regime-exit rules."""

from app.core.exit.stop_engine import evaluate_stop

__all__ = ["evaluate_stop"]
