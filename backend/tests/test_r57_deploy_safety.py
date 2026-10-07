# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R57: deploy scaffolding safety — scheduler/off flags, no write enable, no secrets."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"

COMPOSE = DEPLOY / "docker-compose.prod.yml"
ENV_EXAMPLE = DEPLOY / ".env.prod.example"
DOCKERFILE_API = DEPLOY / "Dockerfile.api"
DOCKERFILE_FE = DEPLOY / "Dockerfile.frontend"
NGINX = DEPLOY / "nginx.conf"

# Patterns that must never appear as enabled / committed secrets in deploy assets.
SECRET_PATTERNS = (
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)BEGIN\s+(RSA\s+)?PRIVATE\s+KEY"),
    re.compile(r"(?i)postgres(?:ql)?://[^:]+:(?!CHANGE_ME)[^@\s]+@"),
    re.compile(r"(?i)ORATS_API_TOKEN\s*=\s*(?!CHANGE_ME|your-|$)[^\s#]+"),
    re.compile(r"(?i)ROBINHOOD_MCP_ACCESS_TOKEN\s*=\s*(?!$|#)[^\s#]+"),
    re.compile(r"(?i)UI_API_KEY\s*=\s*(?!CHANGE_ME)[^\s#]+"),
)

WRITE_ENABLE_PATTERNS = (
    re.compile(r"(?i)trade_execution\s*[:=]\s*[\"']?true"),
    re.compile(r"(?i)manual_only\s*[:=]\s*[\"']?false"),
    re.compile(r"(?i)CHAKRAOPS_SCHEDULER_ENABLED\s*[:=]\s*[\"']?true"),
    re.compile(r"(?i)CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED\s*[:=]\s*[\"']?true"),
    re.compile(r"(?i)CHAKRAOPS_ALLOW_ENV_SCHEDULER_OPT_IN\s*[:=]\s*[\"']?true"),
    re.compile(r"(?i)ENABLE_BROKER_WRITE"),
    re.compile(r"(?i)BROKER_WRITE_ENABLED\s*[:=]\s*[\"']?true"),
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required R57 deploy file: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text() -> str:
    return _read(COMPOSE)


@pytest.fixture(scope="module")
def env_text() -> str:
    return _read(ENV_EXAMPLE)


@pytest.mark.parametrize(
    "path",
    [COMPOSE, ENV_EXAMPLE, DOCKERFILE_API, DOCKERFILE_FE, NGINX],
    ids=lambda p: p.name,
)
def test_deploy_files_exist(path: Path):
    assert path.is_file()


def test_env_example_scheduler_disabled(env_text: str):
    assert "CHAKRAOPS_SCHEDULER_ENABLED=false" in env_text
    assert "CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=false" in env_text
    assert "trade_execution=false" in env_text
    assert "manual_only=true" in env_text
    assert "ROBINHOOD_MCP_TOKEN_PATH=" in env_text
    assert "DATABASE_URL=" in env_text
    assert "UI_API_KEY=" in env_text
    assert "ORATS" in env_text.upper()


def test_compose_fail_closed_overrides(compose_text: str):
    assert "CHAKRAOPS_SCHEDULER_ENABLED" in compose_text
    assert '"false"' in compose_text or ": \"false\"" in compose_text
    assert "trade_execution" in compose_text
    assert "manual_only" in compose_text
    # API must not publish host ports (proxy-only).
    api_block = compose_text.split("api:", 1)[1].split("frontend:", 1)[0]
    assert "ports:" not in api_block
    assert "expose:" in api_block


def test_compose_services_present(compose_text: str):
    for name in ("api:", "frontend:", "postgres:", "monitor:", "cloudflared:"):
        assert name in compose_text
    assert "run_advisory_monitor.py" in compose_text
    assert "uvicorn" in _read(DOCKERFILE_API).lower() or "uvicorn" in compose_text.lower()


def test_nginx_spa_and_api_proxy():
    text = _read(NGINX)
    assert "location /api/" in text
    assert "proxy_pass http://api:8000" in text
    assert "try_files" in text


@pytest.mark.parametrize(
    "path",
    [COMPOSE, ENV_EXAMPLE, DOCKERFILE_API, DOCKERFILE_FE, NGINX],
    ids=lambda p: p.name,
)
def test_no_write_enable_flags(path: Path):
    text = _read(path)
    for pat in WRITE_ENABLE_PATTERNS:
        assert not pat.search(text), f"{path.name} matched write/scheduler enable: {pat.pattern}"


@pytest.mark.parametrize(
    "path",
    [COMPOSE, ENV_EXAMPLE, DOCKERFILE_API, DOCKERFILE_FE, NGINX],
    ids=lambda p: p.name,
)
def test_no_hardcoded_secrets(path: Path):
    text = _read(path)
    for pat in SECRET_PATTERNS:
        assert not pat.search(text), f"{path.name} matched secret-like pattern: {pat.pattern}"


def test_dockerfiles_do_not_copy_dotenv():
    api = _read(DOCKERFILE_API)
    fe = _read(DOCKERFILE_FE)
    for text in (api, fe):
        assert ".env.prod" not in text
        assert "COPY" in text
        # Must not COPY a secrets file into the image
        assert not re.search(r"(?i)COPY\s+[^\n]*\.env", text)
