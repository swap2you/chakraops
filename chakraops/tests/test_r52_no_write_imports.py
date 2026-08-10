# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 static: broker package must not invoke write tool names except denylist strings."""

from __future__ import annotations

from pathlib import Path

WRITE_CALL_MARKERS = (
    "place_equity_order",
    "place_option_order",
    "cancel_equity_order",
    "cancel_option_order",
    "cancel_option_exercise",
    "exercise_option",
)


def test_no_write_tool_invocation_outside_denylist_defs():
    broker_root = Path(__file__).resolve().parents[1] / "app" / "core" / "broker"
    assert broker_root.is_dir()
    allowlist_name = "allowlist.py"
    hits: list[str] = []
    for path in broker_root.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in WRITE_CALL_MARKERS:
            if marker not in text:
                continue
            # Allowed only as string literals in allowlist / status / docs-ish comments in policy.
            if path.name in {allowlist_name, "status.py", "read_only_policy.py", "__init__.py"}:
                continue
            # Any other file mentioning a write tool name is suspicious.
            for i, line in enumerate(text.splitlines(), 1):
                if marker in line and "deny" not in line.lower() and "forbid" not in line.lower():
                    # Still allow quoted denylist mentions in comments
                    if line.strip().startswith("#"):
                        continue
                    if f'"{marker}"' in line or f"'{marker}'" in line:
                        # String only — OK if not call_tool(...)
                        if "call_tool" in line or "invoke" in line.lower():
                            hits.append(f"{path.name}:{i}:{line.strip()}")
                    else:
                        hits.append(f"{path.name}:{i}:{line.strip()}")
    assert hits == [], f"Write tool references outside denylist defs: {hits}"


def test_no_generic_call_robinhood_tool_proxy():
    broker_root = Path(__file__).resolve().parents[1] / "app" / "core" / "broker"
    api_root = Path(__file__).resolve().parents[1] / "app" / "api"
    for root in (broker_root, api_root):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            # Forbid defining/exporting a generic proxy function; docstrings that forbid it are OK.
            if "def call_robinhood_tool" in text or "call_robinhood_tool =" in text:
                raise AssertionError(f"generic proxy found in {path}")
