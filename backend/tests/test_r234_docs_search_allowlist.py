# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4: search_docs returns only allowlisted files; no arbitrary file read."""

import pytest

from app.api.copilot import _search_docs_allowlisted, COPILOT_DOCS_ALLOWLIST, _repo_root


def test_docs_allowlist_contains_only_safe_paths():
    """Allowlist has no secrets, .env, or arbitrary paths."""
    for rel in COPILOT_DOCS_ALLOWLIST:
        assert ".." not in rel
        assert ".env" not in rel.lower()
        assert ".key" not in rel.lower()
        assert rel.endswith(".md") or "release" in rel.lower() or "RELEASE" in rel


def test_search_docs_returns_snippets_from_allowlist():
    """search_docs returns list of { file, line?, excerpt } with file in allowlist."""
    snippets = _search_docs_allowlisted("evaluation", max_total_chars=2000)
    for s in snippets:
        assert "file" in s
        assert s["file"] in COPILOT_DOCS_ALLOWLIST
        assert "excerpt" in s


def test_search_docs_respects_max_total_chars():
    """Total excerpt length is bounded."""
    snippets = _search_docs_allowlisted("release", max_total_chars=500)
    total = sum(len(s.get("excerpt", "")) for s in snippets)
    assert total <= 600  # some slack for structure
