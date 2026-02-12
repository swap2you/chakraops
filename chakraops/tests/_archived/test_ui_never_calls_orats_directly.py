# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Lint guard: UI must never call ORATS directly.

- No file under app/ui/ may import app.core.orats (implementation).
- No file under app/ui/ may import app.data.orats_client (legacy).
- UI must use backend APIs or app.core.data.orats_client (facade) only; this test
  enforces no direct use of the implementation or legacy client.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path


def _collect_ui_python_files() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    ui_dir = root / "app" / "ui"
    if not ui_dir.is_dir():
        return []
    out: list[Path] = []
    for p in ui_dir.rglob("*.py"):
        if p.name.startswith("_"):
            continue
        out.append(p)
    return out


def _forbidden_imports_in_file(path: Path) -> list[str]:
    """Return list of forbidden import strings found in file (e.g. 'app.core.orats')."""
    forbidden: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name and (
                    name == "app.core.orats"
                    or name.startswith("app.core.orats.")
                    or name == "app.data.orats_client"
                    or name.startswith("app.data.orats_client.")
                ):
                    forbidden.append(name)
        if isinstance(node, ast.ImportFrom):
            module = node.module
            if module and (
                module == "app.core.orats"
                or module.startswith("app.core.orats.")
                or module == "app.data.orats_client"
                or module.startswith("app.data.orats_client.")
            ):
                forbidden.append(module)
    return forbidden


def test_ui_never_imports_orats_implementation_or_legacy() -> None:
    """Fail if any app/ui file imports app.core.orats or app.data.orats_client."""
    ui_files = _collect_ui_python_files()
    violations: list[tuple[Path, list[str]]] = []
    for path in ui_files:
        bad = _forbidden_imports_in_file(path)
        if bad:
            violations.append((path, bad))
    rel = Path(__file__).resolve().parent.parent
    msg_parts = []
    for path, imports in violations:
        try:
            rel_path = path.relative_to(rel)
        except ValueError:
            rel_path = path
        msg_parts.append(f"  {rel_path}: {imports}")
    assert not violations, (
        "UI must not call ORATS directly. Use backend APIs or app.core.data.orats_client. "
        "Violations:\n" + "\n".join(msg_parts)
    )
