# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Slack notification module."""

from __future__ import annotations

import os
from typing import Optional

import requests


def send_slack(
    message: str,
    level: str = "INFO",
    webhook_url: Optional[str] = None,
) -> None:
    """Send a message to Slack via webhook.

    Parameters
    ----------
    message:
        Message text to send.
    level:
        Message level: "INFO", "WATCH", or "URGENT" (default: "INFO").
    webhook_url:
        Slack webhook URL. If None, uses SLACK_WEBHOOK_URL from environment.

    Raises
    ------
    ValueError
        If webhook URL is not provided and not found in environment.
    requests.RequestException
        If the HTTP request fails.
    """
    if webhook_url is None:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        raise ValueError(
            "SLACK_WEBHOOK_URL is not set. "
            "Please set it in your environment or pass webhook_url parameter."
        )

    # Format message with level prefix
    level_prefix = level.upper()
    if level_prefix not in ["INFO", "WATCH", "URGENT"]:
        level_prefix = "INFO"
    
    formatted_message = f"[{level_prefix}] {message}"

    # Prepare JSON payload
    payload = {"text": formatted_message}

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ValueError(
            f"Slack webhook returned error {response.status_code}: {response.text}"
        ) from exc
    except requests.RequestException as exc:
        raise ValueError(f"Failed to send Slack message: {exc}") from exc


__all__ = ["send_slack"]
