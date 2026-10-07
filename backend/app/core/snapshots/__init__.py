# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Snapshot archival (EOD freeze). Never read by runtime."""

from app.core.snapshots.freeze import run_freeze_snapshot

__all__ = ["run_freeze_snapshot"]
