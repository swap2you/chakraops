# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R63 deploy compose safety for chakraops.cloud."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "deploy" / "docker-compose.prod.yml"
ENV = REPO / "deploy" / ".env.prod.example"


def test_compose_has_cloudflared_and_mandatory_postgres():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "cloudflared" in text
    assert "cloudflare/cloudflared" in text
    assert "token-file" in text or "TUNNEL_TOKEN" in text or "cloudflare_tunnel_token" in text
    assert "postgres:" in text
    assert 'profiles: ["postgres"]' not in text  # mandatory, not profile-only
    assert "run_advisory_monitor.py" in text
    assert "CHAKRAOPS_SCHEDULER_ENABLED" in text
    assert "trade_execution" in text
    assert "chakraops.cloud" in text
    # API must not publish host ports
    api_block = text.split("api:", 1)[1].split("frontend:", 1)[0]
    assert "ports:" not in api_block
    assert "expose:" in api_block


def test_env_example_production_domain():
    text = ENV.read_text(encoding="utf-8")
    assert "https://chakraops.cloud" in text
    assert "CHAKRAOPS_PRODUCTION=true" in text
    assert "trade_execution=false" in text
    assert "APP_PUBLIC_URL=https://chakraops.cloud" in text
    assert "APP_PUBLIC_URL=https://dauji.info" not in text
