# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 advisor package."""

from app.core.advisor.grounding_r58 import build_goal_plan, build_grounded_answer

__all__ = ["build_grounded_answer", "build_goal_plan"]
