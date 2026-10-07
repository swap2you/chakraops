# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Dedicated ChakraOps local dev ports: defaults, env overrides, and validation."""

from __future__ import annotations

import pytest

from app.core.chakraops_ports import (
    BACKEND_PORT,
    FRONTEND_PORT,
    DEFAULT_BACKEND_PORT,
    DEFAULT_FRONTEND_PORT,
    BACKEND_PORT_ENV,
    FRONTEND_PORT_ENV,
    backend_base_url,
    frontend_origin_default,
    resolve_port,
    resolve_ports,
)


def test_dedicated_ports_are_non_default() -> None:
    assert BACKEND_PORT == 18800
    assert FRONTEND_PORT == 18873
    assert backend_base_url() == "http://127.0.0.1:18800"
    assert frontend_origin_default() == "http://127.0.0.1:18873"


def test_defaults_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_PORT_ENV, raising=False)
    monkeypatch.delenv(FRONTEND_PORT_ENV, raising=False)
    assert resolve_port(BACKEND_PORT_ENV, DEFAULT_BACKEND_PORT) == 18800
    assert resolve_port(FRONTEND_PORT_ENV, DEFAULT_FRONTEND_PORT) == 18873
    assert resolve_ports() == (18800, 18873)


def test_defaults_when_env_empty(monkeypatch) -> None:
    monkeypatch.setenv(BACKEND_PORT_ENV, "")
    monkeypatch.setenv(FRONTEND_PORT_ENV, "   ")
    assert resolve_ports() == (18800, 18873)


def test_valid_override(monkeypatch) -> None:
    monkeypatch.setenv(BACKEND_PORT_ENV, "9001")
    monkeypatch.setenv(FRONTEND_PORT_ENV, "9002")
    assert resolve_ports() == (9001, 9002)


@pytest.mark.parametrize("bad", ["abc", "80a", "1.5", "-5", "  ", "0x10"])
def test_non_numeric_rejected(monkeypatch, bad) -> None:
    monkeypatch.setenv(BACKEND_PORT_ENV, bad)
    if bad.strip() == "":
        # empty falls back to default
        assert resolve_port(BACKEND_PORT_ENV, DEFAULT_BACKEND_PORT) == DEFAULT_BACKEND_PORT
    else:
        with pytest.raises(ValueError):
            resolve_port(BACKEND_PORT_ENV, DEFAULT_BACKEND_PORT)


@pytest.mark.parametrize("bad", ["0", "65536", "99999"])
def test_out_of_range_rejected(monkeypatch, bad) -> None:
    monkeypatch.setenv(BACKEND_PORT_ENV, bad)
    with pytest.raises(ValueError):
        resolve_port(BACKEND_PORT_ENV, DEFAULT_BACKEND_PORT)


def test_equal_ports_rejected(monkeypatch) -> None:
    monkeypatch.setenv(BACKEND_PORT_ENV, "20000")
    monkeypatch.setenv(FRONTEND_PORT_ENV, "20000")
    with pytest.raises(ValueError):
        resolve_ports()
