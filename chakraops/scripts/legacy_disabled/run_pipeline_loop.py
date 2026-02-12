#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Minimal pipeline runner: run decision pipeline on a schedule.

- During market open: every 30s.
- Otherwise: every 300s.
- Writes decision_*.json to the same out_dir the dashboard reads (default: out/).
- Logs one line per run: timestamp, out_file path, symbols_evaluated, selected_signals count.

scripts.live_dashboard runs ONLY Streamlit; it does NOT trigger pipeline runs.
This script is the separate runner that generates decision_*.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _out_dir() -> Path:
    return _repo_root() / "out"


def _latest_decision_file(out_dir: Path) -> Path | None:
    """Return newest decision_*.json by mtime, or None."""
    if not out_dir.exists():
        return None
    files = list(out_dir.glob("decision_*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _stats_from_artifact(path: Path) -> tuple[str, int]:
    """Return (symbols_evaluated_str, selected_signals_count)."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        snap = data.get("decision_snapshot") or {}
        stats = snap.get("stats") or {}
        symbols = stats.get("symbols_evaluated", "?")
        if not isinstance(symbols, (int, str)):
            symbols = "?"
        selected = snap.get("selected_signals") or []
        return (str(symbols), len(selected))
    except Exception:
        return ("?", 0)


def main() -> int:
    repo_root = _repo_root()
    out_dir = _out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from app.market.market_hours import get_eval_interval_seconds
    except ImportError:
        get_eval_interval_seconds = lambda: 300

    print(f"Pipeline loop: out_dir={out_dir.resolve()}", file=sys.stderr)
    print("Log format: timestamp | out_file | symbols_evaluated | selected_count", file=sys.stderr)

    while True:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "scripts.run_and_save", "--output-dir", str(out_dir)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print(f"{ts} | (timeout) | - | -")
            sys.stdout.flush()
        except Exception as e:
            print(f"{ts} | (error: {e}) | - | -")
            sys.stdout.flush()
        else:
            latest = _latest_decision_file(out_dir)
            if latest:
                symbols_str, selected_count = _stats_from_artifact(latest)
                print(f"{ts} | {latest} | {symbols_str} | {selected_count}")
            else:
                print(f"{ts} | (no decision file) | - | -")
            sys.stdout.flush()

        interval = get_eval_interval_seconds()
        time.sleep(interval)


if __name__ == "__main__":
    main()  # runs until interrupted; market-hours polling
