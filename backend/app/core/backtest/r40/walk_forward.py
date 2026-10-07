# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40 walk-forward research runner — fixture / synthetic only (SIMULATION).

Train window freezes params → OOS evaluate. Prevents look-ahead by:
- Fitting / freezing parameters using only dates strictly before OOS start.
- Evaluating OOS trades whose entry_date is inside the OOS window only.
- Never reading future fixture rows when deciding train params.

Does NOT rewrite R27.5 journal backtest. Optional Phase-5 BacktestEngine +
SnapshotCSVDataSource when a snapshot fixture dir is provided; otherwise
uses deterministic synthetic trades from a trades JSON fixture.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core.backtest.r40.fills import FillAssumptions, premium_fill
from app.core.backtest.r40.metrics import TradeRecord, compute_metrics

logger = logging.getLogger(__name__)

SIMULATION_LABEL = "SIMULATION"


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    return date.fromisoformat(s)


def _load_trades_fixture(path: Path) -> List[Dict[str, Any]]:
    """Load trades from JSON list or {trades: [...]} object."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(x) for x in raw]
    if isinstance(raw, Mapping) and isinstance(raw.get("trades"), list):
        return [dict(x) for x in raw["trades"]]
    raise ValueError(f"Unsupported trades fixture format: {path}")


def _filter_trades(
    trades: Sequence[Mapping[str, Any]],
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
    """Keep trades with entry_date in [start, end] inclusive. No look-ahead."""
    out: List[Dict[str, Any]] = []
    for t in trades:
        ed = t.get("entry_date") or t.get("trade_date") or t.get("date")
        if ed is None:
            continue
        d = _parse_date(ed)
        if start <= d <= end:
            out.append(dict(t))
    return out


def _row_to_trade_record(row: Mapping[str, Any], *, bar_index: int) -> TradeRecord:
    pnl = row.get("pnl")
    if pnl is None:
        pnl = row.get("realized_pl") or row.get("realized_pnl") or 0.0
    return TradeRecord(
        pnl=float(pnl),
        premium=float(row.get("premium") or row.get("entry_premium") or 0.0),
        capital=float(row.get("capital") or row.get("collateral") or 0.0),
        assigned=bool(row.get("assigned") or str(row.get("outcome") or "").lower() == "assigned"),
        bar_index=bar_index,
        symbol=str(row.get("symbol") or ""),
        strategy=str(row.get("strategy") or ""),
    )


def freeze_params_from_train(
    train_trades: Sequence[Mapping[str, Any]],
    *,
    profile: str,
) -> Dict[str, Any]:
    """Freeze research params from train window only (no OOS leakage).

    Simple, deterministic freezes — not production threshold retunes:
    - median premium (for fill sanity)
    - train expectancy / win_rate (diagnostic only)
    - profile name echo
    """
    rows = [_row_to_trade_record(t, bar_index=i) for i, t in enumerate(train_trades)]
    premiums = sorted(r.premium for r in rows if r.premium > 0)
    median_prem = premiums[len(premiums) // 2] if premiums else 0.0
    m = compute_metrics(rows)
    return {
        "profile": profile,
        "frozen_from": "train_window",
        "median_premium": round(median_prem, 4),
        "train_expectancy": m.expectancy,
        "train_win_rate": m.win_rate,
        "train_trade_count": m.trade_count,
        "simulation": True,
        "manual_only": True,
        "note": "Params frozen for OOS eval; production profiles remain inherited until evidence exists.",
    }


def _apply_fill_adjustment(
    trades: Sequence[Mapping[str, Any]],
    assumptions: FillAssumptions,
) -> List[Dict[str, Any]]:
    """Recompute premium via fill model when bid/ask present; adjust pnl by delta."""
    out: List[Dict[str, Any]] = []
    for t in trades:
        row = dict(t)
        if row.get("bid") is not None or row.get("ask") is not None or row.get("mid") is not None:
            fill = premium_fill(row, side=str(row.get("side") or "sell"), assumptions=assumptions)
            fp = fill.get("fill_price")
            if fp is not None:
                old = float(row.get("premium") or row.get("entry_premium") or fp)
                delta = float(fp) - old
                # premium credit change flows to pnl (×100 × contracts if provided)
                contracts = int(row.get("contracts") or 1)
                row["premium"] = float(fp)
                row["entry_premium"] = float(fp)
                base_pnl = float(row.get("pnl") or row.get("realized_pl") or 0.0)
                row["pnl"] = base_pnl + delta * 100.0 * contracts
                row["fill_meta"] = fill
        out.append(row)
    return out


def _synthetic_trades_from_snapshots(
    fixture_dir: Path,
    start: date,
    end: date,
    *,
    profile: str,
) -> List[Dict[str, Any]]:
    """Optional Phase-5 SnapshotCSVDataSource path; degrade to empty if unavailable."""
    try:
        from app.backtest.engine import SnapshotCSVDataSource, BacktestEngine, BacktestConfig
    except Exception as e:
        logger.info("[R40] Phase-5 engine unavailable: %s", e)
        return []

    ds = SnapshotCSVDataSource(fixture_dir)
    dates = [d for d in ds.list_dates() if start <= d <= end]
    if not dates:
        return []

    cfg = BacktestConfig(
        data_source=ds,
        strategies=["CSP"],
        fill_model="mid",
        exit_model="hold_to_expiry",
        use_options_layer=False,  # keep offline / deterministic without options selector
        start_date=start,
        end_date=end,
    )
    report = BacktestEngine(cfg).run()
    out: List[Dict[str, Any]] = []
    for i, t in enumerate(report.trades):
        capital = float(t.strike) * 100 * int(t.contracts)
        out.append(
            {
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat(),
                "symbol": t.symbol,
                "strategy": t.strategy,
                "premium": float(t.entry_premium),
                "pnl": float(t.pnl or 0.0),
                "capital": capital,
                "assigned": t.outcome == "assigned",
                "outcome": t.outcome,
                "contracts": t.contracts,
                "profile": profile,
                "source": "phase5_backtest_engine",
                "bar_index": i,
            }
        )
    return out


@dataclass
class WalkForwardResult:
    """Walk-forward SIMULATION result."""

    profile: str
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str
    frozen_params: Dict[str, Any]
    train_metrics: Dict[str, Any]
    oos_metrics: Dict[str, Any]
    train_trades: List[Dict[str, Any]] = field(default_factory=list)
    oos_trades: List[Dict[str, Any]] = field(default_factory=list)
    simulation: bool = True
    manual_only: bool = True
    label: str = SIMULATION_LABEL
    fill_assumptions: Dict[str, Any] = field(default_factory=dict)
    source: str = "fixture"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_walk_forward(
    *,
    profile: str = "balanced",
    fixture_dir: Optional[Path] = None,
    trades_fixture: Optional[Path] = None,
    train_start: str,
    train_end: str,
    oos_start: str,
    oos_end: str,
    account_capital: float = 150_000.0,
    fill_assumptions: Optional[FillAssumptions] = None,
) -> WalkForwardResult:
    """Run fixture-driven walk-forward. Offline only. Labelled SIMULATION.

    Precedence for trade source:
    1. ``trades_fixture`` JSON if provided
    2. ``fixture_dir / trades.json`` if present
    3. Phase-5 SnapshotCSVDataSource over ``fixture_dir`` CSVs
    4. Empty (metrics still returned with zeros / nulls)
    """
    ts, te = _parse_date(train_start), _parse_date(train_end)
    os_, oe = _parse_date(oos_start), _parse_date(oos_end)

    if te >= os_:
        raise ValueError(
            f"Look-ahead guard: train_end ({te}) must be strictly before oos_start ({os_})"
        )
    if ts > te or os_ > oe:
        raise ValueError("Invalid date windows: start must be <= end")

    assum = fill_assumptions or FillAssumptions(slippage_abs=0.01, use_half_spread=False)
    all_trades: List[Dict[str, Any]] = []
    source = "empty"

    fixture_dir_p = Path(fixture_dir) if fixture_dir else None
    trades_path: Optional[Path] = Path(trades_fixture) if trades_fixture else None
    if trades_path is None and fixture_dir_p is not None:
        candidate = fixture_dir_p / "trades.json"
        if candidate.is_file():
            trades_path = candidate

    if trades_path is not None and trades_path.is_file():
        all_trades = _load_trades_fixture(trades_path)
        source = "trades_fixture"
    elif fixture_dir_p is not None and fixture_dir_p.is_dir():
        # Prefer CSV snapshots via Phase-5 engine for the combined window, then split
        all_trades = _synthetic_trades_from_snapshots(fixture_dir_p, ts, oe, profile=profile)
        source = "phase5_snapshots" if all_trades else "empty"

    train_raw = _filter_trades(all_trades, ts, te)
    oos_raw = _filter_trades(all_trades, os_, oe)

    train_adj = _apply_fill_adjustment(train_raw, assum)
    oos_adj = _apply_fill_adjustment(oos_raw, assum)

    frozen = freeze_params_from_train(train_adj, profile=profile)

    train_records = [_row_to_trade_record(t, bar_index=i) for i, t in enumerate(train_adj)]
    oos_records = [_row_to_trade_record(t, bar_index=i) for i, t in enumerate(oos_adj)]

    train_m = compute_metrics(train_records, account_capital=account_capital)
    oos_m = compute_metrics(oos_records, account_capital=account_capital)

    return WalkForwardResult(
        profile=profile,
        train_start=ts.isoformat(),
        train_end=te.isoformat(),
        oos_start=os_.isoformat(),
        oos_end=oe.isoformat(),
        frozen_params=frozen,
        train_metrics=train_m.to_dict(),
        oos_metrics=oos_m.to_dict(),
        train_trades=list(train_adj),
        oos_trades=list(oos_adj),
        simulation=True,
        manual_only=True,
        label=SIMULATION_LABEL,
        fill_assumptions=assum.to_dict(),
        source=source,
    )


def summarize_for_report(result: WalkForwardResult) -> Dict[str, Any]:
    """Compact summary JSON for CLI / API (no large trade dumps by default)."""
    return {
        "simulation": True,
        "manual_only": True,
        "label": SIMULATION_LABEL,
        "profile": result.profile,
        "source": result.source,
        "train": {
            "start": result.train_start,
            "end": result.train_end,
            "metrics": result.train_metrics,
        },
        "oos": {
            "start": result.oos_start,
            "end": result.oos_end,
            "metrics": result.oos_metrics,
        },
        "frozen_params": result.frozen_params,
        "fill_assumptions": result.fill_assumptions,
        "trade_counts": {
            "train": result.train_metrics.get("trade_count", 0),
            "oos": result.oos_metrics.get("trade_count", 0),
        },
    }
