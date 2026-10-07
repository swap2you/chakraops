# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R69 ORATS backtest probe honesty layer — wraps R59; no fake entitlement."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.core.backtest.orats_backtest_probe_r59 import probe_orats_backtest_api


def probe_orats_backtest_honest(*, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    """Strengthen honesty: separate hist/options from backtest; never claim runs without entitlement."""
    base = probe_orats_backtest_api(client=client)
    entitled = bool(base.get("entitled"))
    out = dict(base)
    out.update(
        {
            "schema": "orats_backtest_probe_r69",
            "hist_options_surface_separate": True,
            "auto_purchase": False,
            "can_start_backtest_run": entitled,
            "limitations": [],
        }
    )
    if not entitled:
        out["limitations"].extend(
            [
                "Backtest API not entitled or unreachable — do not fabricate CSP/Wheel backtest results.",
                "Identify exact missing entitlement before proposing another vendor.",
                "Do not confuse /hist/options gaps with backtest API entitlement.",
            ]
        )
        out["research_status"] = "EXTERNAL_GAP"
        out["next_step"] = "Confirm ORATS backtest entitlement with vendor; no automatic purchase."
    else:
        out["research_status"] = "ENTITLED"
        out["next_step"] = "May run official async backtest endpoints; cache/export evidence; still no auto threshold apply."
        out["limitations"].append(
            "Even when entitled, results require walk-forward/OOS and fee/slippage assumptions before calibration proposals."
        )
    out["manual_only"] = True
    out["trade_execution"] = False
    return out
