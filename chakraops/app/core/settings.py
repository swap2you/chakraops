# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Centralized configuration loader for ChakraOps.

Loads config.yaml from the repository root and provides typed access to settings.
Falls back to sensible defaults if config.yaml is missing or incomplete.
Environment variables override config.yaml values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_CACHE: Optional["ChakraOpsConfig"] = None


def _repo_root() -> Path:
    """Return the repository root (chakraops/)."""
    # app/core/config.py -> chakraops/
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ThetaConfig:
    """ThetaData Terminal configuration."""
    base_url: str
    timeout: float
    fallback_enabled: bool
    endpoint: str  # "quote_bulk" (recommended), "ohlc_bulk", "auto"
    strike_limit: int  # Legacy: ignored for bulk endpoints


@dataclass(frozen=True)
class SnapshotConfig:
    """Snapshot retention configuration."""
    retention_days: int
    max_files: int
    output_dir: str


@dataclass(frozen=True)
class RealtimeConfig:
    """Realtime mode configuration."""
    refresh_interval: int
    end_time: str


@dataclass(frozen=True)
class GuardrailsConfig:
    """Optional guardrails (min price enforced; sector/stop-loss/profit advisory)."""
    min_stock_price: float
    max_trades_per_sector: int
    stop_loss_pct: Optional[float]
    profit_target_pct: Optional[float]


@dataclass(frozen=True)
class ChakraOpsConfig:
    """Root configuration object."""
    theta: ThetaConfig
    snapshots: SnapshotConfig
    realtime: RealtimeConfig
    guardrails: GuardrailsConfig
    debug: bool


def _load_yaml_config() -> dict:
    """Load config.yaml from repo root. Returns empty dict if not found."""
    config_path = _repo_root() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_nested(d: dict, *keys, default=None):
    """Safely get nested dict value."""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, {})
    return d if d != {} else default


def load_config(*, reload: bool = False) -> ChakraOpsConfig:
    """Load and return the ChakraOps configuration.
    
    Priority order (highest to lowest):
    1. Environment variables (THETA_REST_URL, THETA_TIMEOUT, THETA_FALLBACK_ENABLED, etc.)
    2. config.yaml values
    3. Built-in defaults
    
    Parameters
    ----------
    reload : bool
        If True, force reload from disk. Otherwise use cached config.
    
    Returns
    -------
    ChakraOpsConfig
        The loaded configuration.
    """
    global _CONFIG_CACHE
    
    if _CONFIG_CACHE is not None and not reload:
        return _CONFIG_CACHE
    
    raw = _load_yaml_config()
    
    # Theta configuration
    theta_raw = raw.get("theta", {}) or {}
    theta_base_url = os.getenv(
        "THETA_REST_URL",
        theta_raw.get("base_url", "http://127.0.0.1:25503/v3")
    ).rstrip("/")
    theta_timeout = float(os.getenv(
        "THETA_TIMEOUT",
        str(theta_raw.get("timeout", 10.0))
    ))
    theta_fallback_str = os.getenv("THETA_FALLBACK_ENABLED", "")
    if theta_fallback_str.lower() in ("true", "1", "yes"):
        theta_fallback = True
    elif theta_fallback_str.lower() in ("false", "0", "no"):
        theta_fallback = False
    else:
        theta_fallback = theta_raw.get("fallback_enabled", True)
    
    # Theta endpoint selection: quote_bulk (recommended), ohlc_bulk, auto
    # Per-strike endpoints are deprecated and don't work for Standard subscriptions
    theta_endpoint = os.getenv(
        "THETA_ENDPOINT",
        theta_raw.get("endpoint", "quote_bulk")
    ).lower()
    if theta_endpoint not in ("ohlc_per_strike", "quote_per_strike", "ohlc_bulk", "quote_bulk", "auto"):
        theta_endpoint = "quote_bulk"
    
    # Strike limit for per-strike modes
    theta_strike_limit = int(os.getenv(
        "THETA_STRIKE_LIMIT",
        str(theta_raw.get("strike_limit", 30))
    ))
    
    theta_config = ThetaConfig(
        base_url=theta_base_url,
        timeout=theta_timeout,
        fallback_enabled=bool(theta_fallback),
        endpoint=theta_endpoint,
        strike_limit=theta_strike_limit,
    )
    
    # Snapshot configuration
    snap_raw = raw.get("snapshots", {}) or {}
    snap_retention_days = int(os.getenv(
        "SNAPSHOT_RETENTION_DAYS",
        str(snap_raw.get("retention_days", 7))
    ))
    snap_max_files = int(os.getenv(
        "SNAPSHOT_MAX_FILES",
        str(snap_raw.get("max_files", 30))
    ))
    snap_output_dir = os.getenv(
        "SNAPSHOT_OUTPUT_DIR",
        snap_raw.get("output_dir", "out")
    )
    
    snapshot_config = SnapshotConfig(
        retention_days=snap_retention_days,
        max_files=snap_max_files,
        output_dir=snap_output_dir,
    )
    
    # Realtime configuration
    realtime_raw = raw.get("realtime", {}) or {}
    realtime_refresh_interval = int(os.getenv(
        "REALTIME_REFRESH_INTERVAL",
        str(realtime_raw.get("refresh_interval", 60))
    ))
    realtime_end_time = os.getenv(
        "REALTIME_END_TIME",
        realtime_raw.get("end_time", "16:00:00")
    )
    
    realtime_config = RealtimeConfig(
        refresh_interval=realtime_refresh_interval,
        end_time=realtime_end_time,
    )
    
    # Guardrails (min_stock_price enforced; sector/stop-loss/profit advisory)
    guardrails_raw = raw.get("guardrails", {}) or {}
    min_stock_price = float(os.getenv(
        "GUARDRAILS_MIN_STOCK_PRICE",
        str(guardrails_raw.get("min_stock_price", 10.0))
    ))
    max_trades_per_sector = int(os.getenv(
        "GUARDRAILS_MAX_TRADES_PER_SECTOR",
        str(guardrails_raw.get("max_trades_per_sector", 3))
    ))
    stop_loss_raw = guardrails_raw.get("stop_loss_percent") or guardrails_raw.get("stop_loss_pct")
    stop_loss_pct = float(stop_loss_raw) if stop_loss_raw is not None else None
    profit_target_raw = guardrails_raw.get("take_profit_percent") or guardrails_raw.get("profit_target_pct")
    profit_target_pct = float(profit_target_raw) if profit_target_raw is not None else None
    guardrails_config = GuardrailsConfig(
        min_stock_price=min_stock_price,
        max_trades_per_sector=max_trades_per_sector,
        stop_loss_pct=stop_loss_pct,
        profit_target_pct=profit_target_pct,
    )
    
    # App-level settings
    app_raw = raw.get("app", {}) or {}
    debug = os.getenv("CHAKRAOPS_DEBUG", "").lower() in ("true", "1", "yes") or \
            app_raw.get("debug", False)
    
    config = ChakraOpsConfig(
        theta=theta_config,
        snapshots=snapshot_config,
        realtime=realtime_config,
        guardrails=guardrails_config,
        debug=bool(debug),
    )
    
    _CONFIG_CACHE = config
    return config


def get_theta_base_url() -> str:
    """Convenience: return Theta base URL from config."""
    return load_config().theta.base_url


def get_theta_timeout() -> float:
    """Convenience: return Theta timeout from config."""
    return load_config().theta.timeout


def is_fallback_enabled() -> bool:
    """Convenience: return whether fallback to snapshot is enabled."""
    return load_config().theta.fallback_enabled


def get_snapshot_retention_days() -> int:
    """Convenience: return snapshot retention days from config."""
    return load_config().snapshots.retention_days


def get_snapshot_max_files() -> int:
    """Convenience: return max snapshot files from config."""
    return load_config().snapshots.max_files


def get_output_dir() -> str:
    """Convenience: return output directory from config."""
    return load_config().snapshots.output_dir


def get_realtime_refresh_interval() -> int:
    """Convenience: return realtime refresh interval from config."""
    return load_config().realtime.refresh_interval


def get_realtime_end_time() -> str:
    """Convenience: return realtime end time from config."""
    return load_config().realtime.end_time


def get_theta_endpoint() -> str:
    """Convenience: return Theta endpoint mode from config.
    
    Returns one of: "quote_bulk" (default), "ohlc_bulk", "auto"
    Per-strike endpoints are deprecated and don't work for Standard subscriptions.
    """
    return load_config().theta.endpoint


def get_theta_strike_limit() -> int:
    """Convenience: return Theta strike limit from config."""
    return load_config().theta.strike_limit


def get_min_stock_price() -> float:
    """Convenience: return minimum stock price guardrail (e.g. avoid penny stocks)."""
    return load_config().guardrails.min_stock_price


def get_max_trades_per_sector() -> int:
    """Convenience: return max trades per sector (advisory diversification)."""
    return load_config().guardrails.max_trades_per_sector


def get_volatility_config() -> dict:
    """Return volatility kill-switch config from config.yaml (Phase 2.2).
    
    Returns dict with vix_threshold, vix_change_pct, range_multiplier.
    Used by regime_gate and volatility_kill_switch.
    """
    raw = _load_yaml_config()
    vol = raw.get("volatility", {}) or {}
    return {
        "vix_threshold": float(vol.get("vix_threshold", 20.0)),
        "vix_change_pct": float(vol.get("vix_change_pct", 20.0)),
        "range_multiplier": float(vol.get("range_multiplier", 2.0)),
    }


def get_confidence_config() -> dict:
    """Return confidence gating config from config.yaml (Phase 2.4).
    
    Returns dict with min_confidence_threshold (0-100). Candidates with
    confidence score below this are excluded from selection.
    """
    raw = _load_yaml_config()
    conf = raw.get("confidence", {}) or {}
    return {
        "min_confidence_threshold": int(conf.get("min_confidence_threshold", 40)),
    }


def get_portfolio_config() -> dict:
    """Return portfolio risk caps from config.yaml (Phase 2.5).
    
    Returns dict with max_active_positions, max_risk_per_trade_pct,
    max_sector_positions, max_total_delta_exposure, account_balance.
    account_balance can be overridden by env PORTFOLIO_ACCOUNT_BALANCE.
    """
    raw = _load_yaml_config()
    port = raw.get("portfolio", {}) or {}
    account = os.getenv("PORTFOLIO_ACCOUNT_BALANCE")
    if account is not None:
        try:
            account_balance = float(account)
        except ValueError:
            account_balance = float(port.get("account_balance", 100_000.0))
    else:
        account_balance = float(port.get("account_balance", 100_000.0))
    return {
        "max_active_positions": int(port.get("max_active_positions", 5)),
        "max_risk_per_trade_pct": float(port.get("max_risk_per_trade_pct", 1.0)),
        "max_sector_positions": int(port.get("max_sector_positions", 2)),
        "max_total_delta_exposure": float(port.get("max_total_delta_exposure", 0.30)),
        "account_balance": account_balance,
        "sector_map": port.get("sector_map") or {},  # optional symbol -> sector
        "max_capital_per_ticker_pct": float(port.get("max_capital_per_ticker_pct", 0.05)),  # Phase 9
    }


def get_environment_config() -> dict:
    """Return environment gate config from config.yaml (Phase 4.5.1–4.5.5).

    earnings_block_window_days: block when days_to_earnings <= this.
    macro_event_block_window_days: block when macro event (FOMC, CPI, etc.) within this many days.
    min_trading_days_to_expiry: block when trading_days_until(expiry) < this.
    block_short_sessions: block new trades on short (early-close) sessions.
    risk_posture: CONSERVATIVE | BALANCED | AGGRESSIVE (Phase 4.5.5; locked to CONSERVATIVE).
    """
    from app.models.risk_posture import RiskPosture

    raw = _load_yaml_config()
    env = raw.get("environment", {}) or {}
    block_short = env.get("block_short_sessions", True)
    if isinstance(block_short, str):
        block_short = block_short.lower() in ("true", "1", "yes")
    # Phase 4.5.5: risk_posture scaffold; locked to CONSERVATIVE (no threshold changes yet)
    rp_raw = (env.get("risk_posture") or "CONSERVATIVE").strip().upper()
    try:
        risk_posture = RiskPosture(rp_raw)
    except ValueError:
        risk_posture = RiskPosture.CONSERVATIVE
    return {
        "earnings_block_window_days": int(env.get("earnings_block_window_days", 7)),
        "macro_event_block_window_days": int(env.get("macro_event_block_window_days", 2)),
        "min_trading_days_to_expiry": int(env.get("min_trading_days_to_expiry", 5)),
        "block_short_sessions": bool(block_short),
        "risk_posture": risk_posture,
    }


def get_run_mode():
    """Return current run mode from env (Phase 6.1). Default DRY_RUN."""
    from app.core.run_mode import RunMode

    raw = os.getenv("RUN_MODE", "").strip().upper()
    if raw == "PAPER_LIVE":
        return RunMode.PAPER_LIVE
    if raw == "LIVE":
        return RunMode.LIVE
    return RunMode.DRY_RUN


def get_options_context_config() -> dict:
    """Return options context gating config from config.yaml (Phase 3.2).

    IV rank: block selling (CSP/credit) when IV rank < min or > max for sells;
    block buying when IV rank > max for buys. Expected move: block if expected
    move exceeds distance from underlying to short strike. Event window: block
    if earnings or macro events within dte_event_window days.
    """
    raw = _load_yaml_config()
    ctx = raw.get("options_context", {}) or {}
    return {
        "iv_rank_min_sell_pct": float(ctx.get("iv_rank_min_sell_pct", 10.0)),
        "iv_rank_max_sell_pct": float(ctx.get("iv_rank_max_sell_pct", 90.0)),
        "iv_rank_max_buy_pct": float(ctx.get("iv_rank_max_buy_pct", 70.0)),
        "dte_event_window": int(ctx.get("dte_event_window", 7)),
        "expected_move_gate": bool(ctx.get("expected_move_gate", True)),
        # Phase 3.3: strategy selection thresholds
        "strategy_iv_rank_high_pct": float(ctx.get("strategy_iv_rank_high_pct", 60.0)),
        "strategy_iv_rank_low_pct": float(ctx.get("strategy_iv_rank_low_pct", 20.0)),
        "strategy_term_slope_backwardation_min": float(ctx.get("strategy_term_slope_backwardation_min", 0.0)),
        "strategy_term_slope_contango_max": float(ctx.get("strategy_term_slope_contango_max", 0.0)),
        "strategy_preference_weight": float(ctx.get("strategy_preference_weight", 0.15)),
    }


__all__ = [
    "ChakraOpsConfig",
    "ThetaConfig",
    "SnapshotConfig",
    "RealtimeConfig",
    "load_config",
    "get_theta_base_url",
    "get_theta_timeout",
    "is_fallback_enabled",
    "get_theta_endpoint",
    "get_theta_strike_limit",
    "get_snapshot_retention_days",
    "get_snapshot_max_files",
    "get_output_dir",
    "get_realtime_refresh_interval",
    "get_realtime_end_time",
    "get_run_mode",
    "get_min_stock_price",
    "get_max_trades_per_sector",
    "get_volatility_config",
    "get_confidence_config",
    "get_portfolio_config",
    "get_environment_config",
    "get_options_context_config",
]
