# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Configuration package for ChakraOps.

This package provides configuration constants organized by domain:
- paths: Database and file system paths
- trade_rules: CSP trading rule constants
- risk_overrides: Risk management override constants
"""

from __future__ import annotations

# Re-export modules for backward compatibility
from . import risk_overrides  # noqa: F401

__all__ = ["risk_overrides"]
