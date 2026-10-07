# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5 backtest engine: snapshot/EOD fixtures only, deterministic, no live calls."""

from __future__ import annotations

import csv
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from app.core.config.trade_rules import MAX_PRICE, MIN_PRICE

logger = logging.getLogger(__name__)


# ---------- Trade model (per PHASE5_STRATEGY_AND_ARCHITECTURE.md 4.1) ----------


@dataclass
class Trade:
    """Simulated trade: strategy, symbol, entry/exit, premiums, strike, expiry, outcome."""

    strategy: str  # "CSP" | "CC"
    symbol: str
    entry_date: date
    exit_date: date
    entry_premium: float
    exit_premium_or_assignment: float  # premium kept/paid or assignment value
    strike: float
    expiry: date
    contracts: int
    outcome: str  # "expired_otm" | "assigned" | "btc"
    # Optional metrics
    regime: Optional[str] = None
    roc: Optional[float] = None
    pnl: Optional[float] = None
    underlying_at_entry: Optional[float] = None
    underlying_at_exit: Optional[float] = None
    days_held: Optional[int] = None


# ---------- Backtest report ----------


@dataclass
class BacktestReport:
    """Aggregate backtest result: P&L, ROC, win rate, drawdown, by symbol/regime."""

    run_id: str
    total_pnl: float
    win_rate: float
    total_trades: int
    wins: int
    losses: int
    roc_mean: Optional[float]
    roc_std: Optional[float]
    max_drawdown: float
    by_symbol: Dict[str, Dict[str, Any]]
    by_regime: Dict[str, Dict[str, Any]]
    trades: List[Trade]
    config_summary: Dict[str, Any] = field(default_factory=dict)


# ---------- Data source protocol ----------


class BacktestDataSource(Protocol):
    """Pluggable backtest data: dated snapshots only, no live calls."""

    def list_dates(self) -> List[date]:
        """Return sorted list of snapshot dates."""
        ...

    def get_snapshot(self, as_of: date) -> Dict[str, Dict[str, Any]]:
        """Return {symbol: {price, volume, iv_rank, ...}} for that date."""
        ...

    def get_regime(self, as_of: date) -> str:
        """Return regime for date, e.g. RISK_ON, RISK_OFF. Default RISK_ON if unknown."""
        ...


# ---------- SnapshotCSVDataSource ----------


class SnapshotCSVDataSource:
    """Reads a folder of dated snapshot CSVs (e.g. 2026-01-01.csv, 2026-01-02.csv)."""

    def __init__(self, base_path: Path, date_fmt: str = "%Y-%m-%d"):
        self.base_path = Path(base_path)
        self.date_fmt = date_fmt

    def list_dates(self) -> List[date]:
        out: List[date] = []
        for p in self.base_path.glob("*.csv"):
            try:
                # Try YYYY-MM-DD from stem
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                pass
        out.sort()
        return out

    def get_snapshot(self, as_of: date) -> Dict[str, Dict[str, Any]]:
        path = self.base_path / f"{as_of.isoformat()}.csv"
        if not path.exists():
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        with open(path, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                sym = (row.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                try:
                    price = float(row.get("price") or 0)
                except (TypeError, ValueError):
                    price = 0.0
                try:
                    vol = int(float(row.get("volume") or 0))
                except (TypeError, ValueError):
                    vol = 0
                try:
                    iv = float(row.get("iv_rank") or 0)
                except (TypeError, ValueError):
                    iv = 0.0
                result[sym] = {"price": price, "volume": vol, "iv_rank": iv}
        return result

    def get_regime(self, as_of: date) -> str:
        """Default RISK_ON for backtest when no regime series is stored."""
        return "RISK_ON"


# ---------- Synthetic options provider for backtest (no live chain) ----------


class SyntheticOptionsChainProvider:
    """Deterministic chain for backtest: one put per symbol, expiry as_of + dte_days."""

    def __init__(self, as_of: date, get_price: Callable[[str], float], dte_days: int = 35):
        self.as_of = as_of
        self.get_price = get_price
        self.dte_days = dte_days

    def get_expirations(self, symbol: str) -> List[date]:
        return [self.as_of + timedelta(days=self.dte_days)]

    def get_chain(self, symbol: str, expiry: date, right: str) -> List[Dict[str, Any]]:
        if (right or "").upper() != "P":
            return []
        price = self.get_price(symbol)
        if price <= 0:
            return []
        strike = round(price * 0.98, 2)
        if strike < 1:
            strike = round(price, 2)
        mid = max(0.01, round(strike * 0.005, 2))
        return [
            {
                "strike": strike,
                "bid": mid - 0.02,
                "ask": mid + 0.02,
                "delta": -0.25,
                "iv": 0.22,
                "volume": 100,
                "open_interest": 500,
            }
        ]


# ---------- Stock-level eligibility (match heartbeat gates) ----------


def _stock_eligible(
    price: Optional[float],
    volume: Optional[int],
    iv_rank: Optional[float],
    regime: str,
) -> bool:
    if price is None or price <= 0:
        return False
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    if regime in ("RISK_OFF", "UNKNOWN"):
        return False
    if volume is not None and volume < 1_000_000:
        return False
    if iv_rank is not None and iv_rank < 20:
        return False
    return True


# ---------- BacktestEngine ----------


@dataclass
class BacktestConfig:
    """Backtest run config: data source, strategies, fill/exit rules."""

    data_source: BacktestDataSource
    strategies: List[str] = field(default_factory=lambda: ["CSP"])
    fill_model: str = "mid"  # "mid" | "close"
    exit_model: str = "hold_to_expiry"
    use_options_layer: bool = True
    btc_rule_enabled: bool = False
    contracts_per_entry: int = 1
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    output_dir: Optional[Path] = None


class BacktestEngine:
    """Runs backtest over snapshot dates; no live data. Writes report + trades CSV."""

    def __init__(self, config: BacktestConfig):
        self.config = config

    def run(self, config: Optional[BacktestConfig] = None) -> BacktestReport:
        cfg = config or self.config
        run_id = str(uuid.uuid4())[:8]
        dates = cfg.data_source.list_dates()
        if cfg.start_date:
            dates = [d for d in dates if d >= cfg.start_date]
        if cfg.end_date:
            dates = [d for d in dates if d <= cfg.end_date]
        if not dates:
            return BacktestReport(
                run_id=run_id,
                total_pnl=0.0,
                win_rate=0.0,
                total_trades=0,
                wins=0,
                losses=0,
                roc_mean=None,
                roc_std=None,
                max_drawdown=0.0,
                by_symbol={},
                by_regime={},
                trades=[],
                config_summary={"reason": "no_dates_in_range"},
            )

        trades: List[Trade] = []
        open_positions: Dict[str, Trade] = {}  # symbol -> entry trade (single-symbol, one at a time)
        fill_model = (cfg.fill_model or "mid").lower()
        use_options = cfg.use_options_layer
        contracts = max(1, cfg.contracts_per_entry)

        # Optional import for options layer
        select_csp_contract = None
        if use_options:
            try:
                from app.core.options.contract_selector import select_csp_contract as _sel
                select_csp_contract = _sel
            except Exception as e:
                logger.warning("[BACKTEST] Options layer unavailable: %s", e)
                use_options = False

        for d in dates:
            snapshot = cfg.data_source.get_snapshot(d)
            regime = cfg.data_source.get_regime(d)
            if regime != "RISK_ON":
                continue

            # Resolve expiries for open positions (hold to expiry)
            to_close: List[str] = []
            for sym, pos in list(open_positions.items()):
                if pos.expiry <= d:
                    to_close.append(sym)
            for sym in to_close:
                pos = open_positions.pop(sym)
                row = snapshot.get(sym, {})
                underlying_exit = float(row.get("price") or 0)
                # Exit: hold to expiry -> OTM keep premium; ITM assignment
                if pos.strike > underlying_exit:
                    outcome = "expired_otm"
                    exit_premium = 0.0
                    pnl = pos.entry_premium * contracts * 100
                else:
                    outcome = "assigned"
                    exit_premium = 0.0
                    # CSP assigned: we “receive” stock at strike; backtest PnL = premium kept (cost basis = strike)
                    pnl = pos.entry_premium * contracts * 100
                days_held = (d - pos.entry_date).days
                t = Trade(
                    strategy=pos.strategy,
                    symbol=pos.symbol,
                    entry_date=pos.entry_date,
                    exit_date=d,
                    entry_premium=pos.entry_premium,
                    exit_premium_or_assignment=exit_premium,
                    strike=pos.strike,
                    expiry=pos.expiry,
                    contracts=pos.contracts,
                    outcome=outcome,
                    regime=regime,
                    roc=pos.roc,
                    pnl=pnl,
                    underlying_at_entry=pos.underlying_at_entry,
                    underlying_at_exit=underlying_exit,
                    days_held=days_held,
                )
                trades.append(t)

            # Entry: first date symbol passes stock + options
            for symbol, row in snapshot.items():
                if symbol in open_positions:
                    continue
                price = row.get("price")
                volume = row.get("volume")
                iv_rank = row.get("iv_rank")
                if not _stock_eligible(price, volume, iv_rank, regime):
                    continue

                chosen = None
                if use_options and select_csp_contract and "CSP" in (cfg.strategies or ["CSP"]):
                    provider = SyntheticOptionsChainProvider(
                        d, lambda s, _sym=symbol, _r=row: float(_r.get("price") or 0) if s == _sym else 0.0
                    )
                    ctx = {
                        "price": price,
                        "iv_rank": iv_rank,
                        "regime": regime,
                        "as_of_date": d,
                    }
                    r = select_csp_contract(symbol, ctx, provider, None)
                    if not r.eligible:
                        continue
                    chosen = r.chosen_contract
                    if not chosen:
                        continue
                elif "CSP" in (cfg.strategies or ["CSP"]):
                    # No options layer: synthetic contract for backtest
                    expiry = d + timedelta(days=35)
                    strike = round(float(price or 0) * 0.98, 2) if price else 0
                    mid = max(0.01, strike * 0.005)
                    chosen = {"strike": strike, "expiry": expiry.isoformat(), "mid": mid, "right": "P"}
                else:
                    continue

                try:
                    strike = float(chosen["strike"])
                    expiry = chosen.get("expiry")
                    if isinstance(expiry, str):
                        exp_date = date.fromisoformat(expiry[:10])
                    else:
                        exp_date = d + timedelta(days=35)
                    entry_premium = float(chosen.get("mid") or 0)
                    if fill_model == "close":
                        entry_premium = entry_premium  # no separate close series; keep mid
                    roc = entry_premium / strike if strike else 0
                except (TypeError, ValueError, KeyError):
                    continue

                open_positions[symbol] = Trade(
                    strategy="CSP",
                    symbol=symbol,
                    entry_date=d,
                    exit_date=d,
                    entry_premium=entry_premium,
                    exit_premium_or_assignment=0.0,
                    strike=strike,
                    expiry=exp_date,
                    contracts=contracts,
                    outcome="open",
                    regime=regime,
                    roc=roc,
                    pnl=None,
                    underlying_at_entry=float(price or 0),
                    underlying_at_exit=None,
                    days_held=None,
                )

        # Close any remaining open at end of range
        last_date = dates[-1]
        for sym, pos in list(open_positions.items()):
            snapshot = cfg.data_source.get_snapshot(last_date)
            row = snapshot.get(sym, {})
            underlying_exit = float(row.get("price") or 0)
            if pos.strike > underlying_exit:
                outcome, pnl = "expired_otm", pos.entry_premium * contracts * 100
            else:
                outcome, pnl = "assigned", pos.entry_premium * contracts * 100
            trades.append(Trade(
                strategy=pos.strategy,
                symbol=pos.symbol,
                entry_date=pos.entry_date,
                exit_date=last_date,
                entry_premium=pos.entry_premium,
                exit_premium_or_assignment=0.0,
                strike=pos.strike,
                expiry=pos.expiry,
                contracts=pos.contracts,
                outcome=outcome,
                regime=pos.regime,
                roc=pos.roc,
                pnl=pnl,
                underlying_at_entry=pos.underlying_at_entry,
                underlying_at_exit=underlying_exit,
                days_held=(last_date - pos.entry_date).days,
            ))

        # Metrics
        closed = [t for t in trades if t.outcome in ("expired_otm", "assigned", "btc")]
        pnls = [t.pnl for t in closed if t.pnl is not None]
        total_pnl = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p <= 0)
        total_trades = len(closed)
        win_rate = (wins / total_trades) if total_trades else 0.0
        rocs = [t.roc for t in closed if t.roc is not None]
        roc_mean = (sum(rocs) / len(rocs)) if rocs else None
        roc_std = None
        if len(rocs) > 1:
            import math
            mean = sum(rocs) / len(rocs)
            var = sum((x - mean) ** 2 for x in rocs) / (len(rocs) - 1)
            roc_std = math.sqrt(var)

        # Max drawdown (cumulative PnL)
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(closed, key=lambda x: x.exit_date):
            cum += (t.pnl or 0)
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)

        by_symbol: Dict[str, Dict[str, Any]] = {}
        for t in closed:
            s = t.symbol
            if s not in by_symbol:
                by_symbol[s] = {"pnl": 0.0, "trades": 0, "wins": 0}
            by_symbol[s]["pnl"] += (t.pnl or 0)
            by_symbol[s]["trades"] += 1
            if (t.pnl or 0) > 0:
                by_symbol[s]["wins"] += 1
        by_regime: Dict[str, Dict[str, Any]] = {}
        for t in closed:
            r = t.regime or "UNKNOWN"
            if r not in by_regime:
                by_regime[r] = {"pnl": 0.0, "trades": 0}
            by_regime[r]["pnl"] += (t.pnl or 0)
            by_regime[r]["trades"] += 1

        report = BacktestReport(
            run_id=run_id,
            total_pnl=total_pnl,
            win_rate=win_rate,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            roc_mean=roc_mean,
            roc_std=roc_std,
            max_drawdown=abs(max_dd),
            by_symbol=by_symbol,
            by_regime=by_regime,
            trades=closed,
            config_summary={
                "fill_model": fill_model,
                "exit_model": cfg.exit_model,
                "use_options_layer": use_options,
                "strategies": cfg.strategies,
            },
        )

        # Write outputs: app/data/backtests/<run_id>/
        try:
            from app.core.config.paths import BASE_DIR
            _default_base = BASE_DIR / "app" / "data" / "backtests"
        except Exception:
            _default_base = Path(__file__).resolve().parents[1] / "data" / "backtests"
        _base = Path(cfg.output_dir) if cfg.output_dir else _default_base
        out_dir = _base / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        self._write_report(report, out_dir)
        self._write_trades_csv(report.trades, out_dir)
        return report

    def _write_report(self, report: BacktestReport, out_dir: Path) -> None:
        d = {
            "run_id": report.run_id,
            "total_pnl": report.total_pnl,
            "win_rate": report.win_rate,
            "total_trades": report.total_trades,
            "wins": report.wins,
            "losses": report.losses,
            "roc_mean": report.roc_mean,
            "roc_std": report.roc_std,
            "max_drawdown": report.max_drawdown,
            "by_symbol": report.by_symbol,
            "by_regime": report.by_regime,
            "config_summary": report.config_summary,
        }
        with open(out_dir / "backtest_report.json", "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)

    def _write_trades_csv(self, trades: List[Trade], out_dir: Path) -> None:
        path = out_dir / "backtest_trades.csv"
        if not trades:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write("strategy,symbol,entry_date,exit_date,entry_premium,strike,expiry,contracts,outcome,roc,pnl,regime,days_held\n")
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "strategy", "symbol", "entry_date", "exit_date", "entry_premium",
                "exit_premium_or_assignment", "strike", "expiry", "contracts",
                "outcome", "roc", "pnl", "regime", "days_held",
                "underlying_at_entry", "underlying_at_exit",
            ])
            w.writeheader()
            for t in trades:
                w.writerow({
                    "strategy": t.strategy,
                    "symbol": t.symbol,
                    "entry_date": t.entry_date.isoformat(),
                    "exit_date": t.exit_date.isoformat(),
                    "entry_premium": t.entry_premium,
                    "exit_premium_or_assignment": t.exit_premium_or_assignment,
                    "strike": t.strike,
                    "expiry": t.expiry.isoformat(),
                    "contracts": t.contracts,
                    "outcome": t.outcome,
                    "roc": t.roc,
                    "pnl": t.pnl,
                    "regime": t.regime,
                    "days_held": t.days_held,
                    "underlying_at_entry": t.underlying_at_entry,
                    "underlying_at_exit": t.underlying_at_exit,
                })


__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestReport",
    "BacktestDataSource",
    "SnapshotCSVDataSource",
    "SyntheticOptionsChainProvider",
    "Trade",
]
