"""R32.0 C-1: ORATS token must be environment-only with no hardcoded value.

Verifies:
- No hardcoded token literal remains in app/core/config/orats_secrets.py.
- get_orats_token() resolves from the environment (ORATS_API_TOKEN / ORATS_API_KEY).
- get_orats_token(required=True) raises a clear error (without the value) when unset.
- The ORATS_API_TOKEN module attribute still exists for backward-compatible patching.
"""
import re
from pathlib import Path

import pytest

from app.core.config import orats_secrets


SECRETS_PATH = Path(orats_secrets.__file__)


def test_no_hardcoded_token_literal_in_source():
    src = SECRETS_PATH.read_text(encoding="utf-8")
    # No UUID-style token literal.
    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", src)
    # No assignment of a long quoted literal to ORATS_API_TOKEN.
    assert not re.search(r'ORATS_API_TOKEN\s*=\s*["\'][^"\']{16,}["\']', src)


def test_module_attribute_exists_for_patch_compat():
    assert hasattr(orats_secrets, "ORATS_API_TOKEN")


def test_get_orats_token_reads_env(monkeypatch):
    # Clear the import-time module attribute so the live env read is exercised.
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.setenv("ORATS_API_TOKEN", "env-token-value")
    assert orats_secrets.get_orats_token() == "env-token-value"


def test_get_orats_token_reads_key_alias(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.setenv("ORATS_API_KEY", "alias-token-value")
    assert orats_secrets.get_orats_token() == "alias-token-value"


def test_get_orats_token_prefers_module_attribute(monkeypatch):
    # An explicit module attribute (test patch / configured override) wins.
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", "patched-token")
    monkeypatch.setenv("ORATS_API_TOKEN", "env-token-value")
    assert orats_secrets.get_orats_token() == "patched-token"


def test_get_orats_token_missing_returns_none(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_KEY", raising=False)
    assert orats_secrets.get_orats_token() is None


def test_get_orats_token_required_raises_without_value(monkeypatch):
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        orats_secrets.get_orats_token(required=True)
    msg = str(exc.value)
    assert "ORATS_API_TOKEN is not set" in msg
    # Error message must not leak any token-like value.
    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-", msg)
