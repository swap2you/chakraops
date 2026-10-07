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


@dataclass(frozen=True)
class SnapshotConfig:
    """Snapshot retention configuration."""
    retention_days: int
    max_files: int
    output_dir: str


@dataclass(frozen=True)
class ChakraOpsConfig:
    """Root configuration object."""
    theta: ThetaConfig
    snapshots: SnapshotConfig
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
    
    theta_config = ThetaConfig(
        base_url=theta_base_url,
        timeout=theta_timeout,
        fallback_enabled=bool(theta_fallback),
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
    
    # App-level settings
    app_raw = raw.get("app", {}) or {}
    debug = os.getenv("CHAKRAOPS_DEBUG", "").lower() in ("true", "1", "yes") or \
            app_raw.get("debug", False)
    
    config = ChakraOpsConfig(
        theta=theta_config,
        snapshots=snapshot_config,
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


__all__ = [
    "ChakraOpsConfig",
    "ThetaConfig",
    "SnapshotConfig",
    "load_config",
    "get_theta_base_url",
    "get_theta_timeout",
    "is_fallback_enabled",
    "get_snapshot_retention_days",
    "get_snapshot_max_files",
    "get_output_dir",
]
