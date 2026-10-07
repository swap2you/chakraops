# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R59 ORATS Backtest API entitlement probe — never logs tokens."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

# Official ORATS backtest surface (probe only; do not assume entitlement).
ORATS_BACKTEST_BASE = os.environ.get("ORATS_BACKTEST_BASE", "https://api.orats.io").rstrip("/")


def _token() -> str:
    return (os.environ.get("ORATS_TOKEN") or os.environ.get("ORATS_API_TOKEN") or "").strip()


def probe_orats_backtest_api(*, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    """Probe ORATS backtest entitlement without logging secrets.

    Returns honest EXTERNAL_GAP when 401/403/404 or missing token.
    """
    token = _token()
    out: Dict[str, Any] = {
        "provider": "orats",
        "surface": "backtest_api",
        "manual_only": True,
        "trade_execution": False,
        "token_present": bool(token),
    }
    if not token:
        out.update(
            {
                "status": "EXTERNAL_GAP",
                "code": "ORATS_BACKTEST_TOKEN_MISSING",
                "entitled": False,
            }
        )
        return out

    url = f"{ORATS_BACKTEST_BASE}/api/backtests"
    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"}
    # Some ORATS endpoints use query token — never log either form.
    try:
        own = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.get(url, headers=headers, params={"token": token})
        finally:
            if own:
                http.close()
        status = int(resp.status_code)
        out["http_status"] = status
        if status in (401, 403):
            out.update(
                {
                    "status": "EXTERNAL_GAP",
                    "code": "ORATS_BACKTEST_ENTITLEMENT_GAP",
                    "entitled": False,
                }
            )
        elif status == 404:
            out.update(
                {
                    "status": "EXTERNAL_GAP",
                    "code": "ORATS_BACKTEST_ENDPOINT_NOT_FOUND",
                    "entitled": False,
                    "note": "Endpoint path may differ; treat as not entitled until confirmed.",
                }
            )
        elif 200 <= status < 300:
            out.update({"status": "OK", "code": "ORATS_BACKTEST_AVAILABLE", "entitled": True})
        else:
            out.update(
                {
                    "status": "EXTERNAL_GAP",
                    "code": f"ORATS_BACKTEST_HTTP_{status}",
                    "entitled": False,
                }
            )
    except Exception as exc:
        out.update(
            {
                "status": "EXTERNAL_GAP",
                "code": "ORATS_BACKTEST_PROBE_ERROR",
                "entitled": False,
                "error_type": type(exc).__name__,
            }
        )
    return out
