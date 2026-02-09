# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: FastAPI server for React frontend - market-status, view endpoints, ops/evaluate, symbol-diagnostics."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Load .env first so OPENAI_API_KEY, SLACK_WEBHOOK_URL, etc. are available (for uvicorn and run_api)
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # 1) Repo root .env (chakraops/.env) — primary; override so file wins over empty shell vars
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _env_file = _repo_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=True)
    # 2) Current working directory .env (e.g. if started from workspace root)
    load_dotenv()


_load_env()

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.market_status import read_market_status
from app.api.views_loader import (
    build_daily_overview_from_artifact,
    get_alerts_for_api,
    get_decision_history_for_api,
    get_positions_for_api,
    load_decision_artifact,
)
from app.market.market_hours import get_eval_interval_seconds, get_market_phase, is_market_open

logger = logging.getLogger(__name__)

# Cooldown: 5 min between evaluate triggers (global)
EVAL_COOLDOWN_SEC = 300
_last_eval_ts: float = 0
_eval_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

# ============================================================================
# BACKGROUND SCHEDULER FOR UNIVERSE EVALUATION
# ============================================================================

# Scheduler interval: default 15 minutes. Recommended 15, 30, or 60. Set UNIVERSE_EVAL_MINUTES (1-120).
_UNIVERSE_EVAL_MINUTES_RAW = int(os.getenv("UNIVERSE_EVAL_MINUTES", "15"))
UNIVERSE_EVAL_MINUTES = max(1, min(120, _UNIVERSE_EVAL_MINUTES_RAW))
_scheduler_stop_event: Optional[threading.Event] = None
_scheduler_thread: Optional[threading.Thread] = None
_last_scheduled_eval_at: Optional[str] = None

# ============================================================================
# NIGHTLY SCHEDULER
# ============================================================================

# Nightly evaluation time: default 19:00 ET. Set NIGHTLY_EVAL_TIME (HH:MM).
NIGHTLY_EVAL_TIME = os.getenv("NIGHTLY_EVAL_TIME", "19:00")
NIGHTLY_EVAL_TZ = os.getenv("NIGHTLY_EVAL_TZ", "America/New_York")
NIGHTLY_EVAL_ENABLED = os.getenv("NIGHTLY_EVAL_ENABLED", "true").lower() in ("true", "1", "yes")
_nightly_stop_event: Optional[threading.Event] = None
_nightly_thread: Optional[threading.Thread] = None
_last_nightly_eval_at: Optional[str] = None


def _get_next_nightly_time() -> datetime:
    """Get the next scheduled nightly evaluation time."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    
    tz = ZoneInfo(NIGHTLY_EVAL_TZ)
    now = datetime.now(tz)
    
    # Parse time
    try:
        hour, minute = map(int, NIGHTLY_EVAL_TIME.split(":"))
    except ValueError:
        hour, minute = 19, 0
    
    # Next occurrence
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Already passed today, schedule for tomorrow
        from datetime import timedelta
        target = target + timedelta(days=1)
    
    return target


def _run_nightly_evaluation() -> bool:
    """
    Run the nightly evaluation.
    Returns True if run was triggered.
    """
    global _last_nightly_eval_at
    
    try:
        from app.core.eval.nightly_evaluation import NightlyConfig, run_nightly_evaluation
        
        logger.info("[NIGHTLY] Starting nightly evaluation")
        print("[NIGHTLY] Starting nightly evaluation")
        
        config = NightlyConfig.from_env()
        result = run_nightly_evaluation(config=config, asof="last_close")
        
        if result.get("success"):
            _last_nightly_eval_at = datetime.now(timezone.utc).isoformat()
            logger.info("[NIGHTLY] Completed: run_id=%s", result.get("run_id"))
            print(f"[NIGHTLY] Completed: run_id={result.get('run_id')}")
            return True
        else:
            logger.warning("[NIGHTLY] Failed: %s", result.get("error"))
            return False
    except Exception as e:
        logger.exception("[NIGHTLY] Error: %s", e)
        return False


def _nightly_scheduler_loop(stop_event: threading.Event) -> None:
    """
    Nightly scheduler loop.
    Waits until the scheduled time and triggers nightly evaluation.
    """
    logger.info("[NIGHTLY_SCHEDULER] Started for %s %s", NIGHTLY_EVAL_TIME, NIGHTLY_EVAL_TZ)
    print(f"[NIGHTLY_SCHEDULER] Started for {NIGHTLY_EVAL_TIME} {NIGHTLY_EVAL_TZ}")
    
    while not stop_event.is_set():
        # Calculate time until next run
        try:
            next_time = _get_next_nightly_time()
            now = datetime.now(next_time.tzinfo)
            wait_seconds = (next_time - now).total_seconds()
            
            if wait_seconds > 0:
                logger.debug("[NIGHTLY_SCHEDULER] Next run at %s (in %ds)", next_time.isoformat(), int(wait_seconds))
                
                # Wait in chunks to be responsive to shutdown
                while wait_seconds > 0 and not stop_event.is_set():
                    chunk = min(60, wait_seconds)  # Check every minute
                    stop_event.wait(chunk)
                    wait_seconds -= chunk
            
            if stop_event.is_set():
                break
            
            # Run nightly evaluation
            _run_nightly_evaluation()
            
            # Sleep a bit to avoid re-triggering
            stop_event.wait(120)  # 2 minutes
            
        except Exception as e:
            logger.exception("[NIGHTLY_SCHEDULER] Error in loop: %s", e)
            stop_event.wait(300)  # Wait 5 minutes on error
    
    logger.info("[NIGHTLY_SCHEDULER] Stopped")
    print("[NIGHTLY_SCHEDULER] Stopped")


def start_nightly_scheduler() -> None:
    """Start the nightly evaluation scheduler."""
    global _nightly_stop_event, _nightly_thread
    
    if not NIGHTLY_EVAL_ENABLED:
        logger.info("[NIGHTLY_SCHEDULER] Disabled via NIGHTLY_EVAL_ENABLED=false")
        return
    
    if _nightly_thread is not None and _nightly_thread.is_alive():
        logger.warning("[NIGHTLY_SCHEDULER] Already running")
        return
    
    _nightly_stop_event = threading.Event()
    _nightly_thread = threading.Thread(
        target=_nightly_scheduler_loop,
        args=(_nightly_stop_event,),
        daemon=True,
        name="NightlyScheduler",
    )
    _nightly_thread.start()


def stop_nightly_scheduler() -> None:
    """Stop the nightly evaluation scheduler."""
    global _nightly_stop_event, _nightly_thread
    
    if _nightly_stop_event is not None:
        logger.info("[NIGHTLY_SCHEDULER] Signaling stop...")
        _nightly_stop_event.set()
    
    if _nightly_thread is not None and _nightly_thread.is_alive():
        _nightly_thread.join(timeout=5.0)
        if _nightly_thread.is_alive():
            logger.warning("[NIGHTLY_SCHEDULER] Thread did not stop within timeout")
    
    _nightly_stop_event = None
    _nightly_thread = None


def get_nightly_scheduler_status() -> Dict[str, Any]:
    """Get nightly scheduler status."""
    next_time = None
    try:
        if NIGHTLY_EVAL_ENABLED:
            next_time = _get_next_nightly_time().isoformat()
    except Exception:
        pass
    
    return {
        "enabled": NIGHTLY_EVAL_ENABLED,
        "running": _nightly_thread is not None and _nightly_thread.is_alive(),
        "eval_time": NIGHTLY_EVAL_TIME,
        "timezone": NIGHTLY_EVAL_TZ,
        "next_scheduled_at": next_time,
        "last_nightly_eval_at": _last_nightly_eval_at,
    }


def _run_scheduled_evaluation() -> bool:
    """
    Attempt to run a scheduled evaluation.
    Returns True if evaluation was triggered, False otherwise.
    """
    global _last_scheduled_eval_at
    
    # Check if market is open
    phase = get_market_phase()
    if phase != "OPEN":
        logger.debug("[SCHEDULER] Market phase is %s, skipping evaluation", phase)
        return False
    
    # Try to trigger evaluation
    try:
        from app.api.data_health import UNIVERSE_SYMBOLS
        from app.core.eval.universe_evaluator import trigger_evaluation, get_evaluation_state
        
        # Check if already running
        state = get_evaluation_state()
        if state.get("evaluation_state") == "RUNNING":
            logger.debug("[SCHEDULER] Evaluation already running, skipping")
            return False
        
        if not UNIVERSE_SYMBOLS:
            logger.warning("[SCHEDULER] Universe is empty, skipping evaluation")
            return False
        
        result = trigger_evaluation(list(UNIVERSE_SYMBOLS))
        if result.get("started"):
            _last_scheduled_eval_at = datetime.now(timezone.utc).isoformat()
            logger.info("[SCHEDULER] Triggered scheduled evaluation at %s", _last_scheduled_eval_at)
            print(f"[SCHEDULER] Triggered scheduled evaluation at {_last_scheduled_eval_at}")
            return True
        else:
            logger.debug("[SCHEDULER] Evaluation not started: %s", result.get("reason"))
            return False
    except ImportError as e:
        logger.warning("[SCHEDULER] Cannot import evaluation modules: %s", e)
        return False
    except Exception as e:
        logger.exception("[SCHEDULER] Error triggering evaluation: %s", e)
        return False


def _scheduler_loop(stop_event: threading.Event, interval_minutes: int) -> None:
    """
    Background scheduler loop.
    Runs every interval_minutes and triggers evaluation if market is open.
    """
    interval_seconds = interval_minutes * 60
    logger.info("[SCHEDULER] Started with interval %d minutes (%d seconds)", interval_minutes, interval_seconds)
    print(f"[SCHEDULER] Started with interval {interval_minutes} minutes")
    
    while not stop_event.is_set():
        # Wait for the interval (or until stop is signaled)
        # Check more frequently to be responsive to shutdown
        wait_step = min(30, interval_seconds)  # Check every 30s at most
        waited = 0
        while waited < interval_seconds and not stop_event.is_set():
            stop_event.wait(wait_step)
            waited += wait_step
        
        if stop_event.is_set():
            break
        
        # Attempt scheduled evaluation
        _run_scheduled_evaluation()
    
    logger.info("[SCHEDULER] Stopped")
    print("[SCHEDULER] Stopped")


def start_evaluation_scheduler() -> None:
    """Start the background evaluation scheduler."""
    global _scheduler_stop_event, _scheduler_thread
    
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        logger.warning("[SCHEDULER] Already running")
        return
    
    _scheduler_stop_event = threading.Event()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(_scheduler_stop_event, UNIVERSE_EVAL_MINUTES),
        daemon=True,
        name="EvalScheduler",
    )
    _scheduler_thread.start()


def stop_evaluation_scheduler() -> None:
    """Stop the background evaluation scheduler."""
    global _scheduler_stop_event, _scheduler_thread
    
    if _scheduler_stop_event is not None:
        logger.info("[SCHEDULER] Signaling stop...")
        _scheduler_stop_event.set()
    
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5.0)
        if _scheduler_thread.is_alive():
            logger.warning("[SCHEDULER] Thread did not stop within timeout")
    
    _scheduler_stop_event = None
    _scheduler_thread = None


def get_scheduler_status() -> Dict[str, Any]:
    """Get current scheduler status."""
    return {
        "running": _scheduler_thread is not None and _scheduler_thread.is_alive(),
        "interval_minutes": UNIVERSE_EVAL_MINUTES,
        "last_scheduled_eval_at": _last_scheduled_eval_at,
        "market_open": is_market_open(),
    }

def _collect_api_routes(app: FastAPI) -> list:
    """Return list of API route dicts: path, methods, name. Only paths starting with /api/."""
    out = []
    for r in getattr(app, "routes", []):
        path = getattr(r, "path", None)
        if not path or not path.startswith("/api/"):
            continue
        methods = list(getattr(r, "methods", set) or [])
        name = getattr(r, "name", "") or ""
        out.append({"path": path, "methods": sorted(methods), "name": name})
    return out


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: ORATS token (hardcoded), boot probe, route count, scheduler. No token validation."""
    logger.info("[CONFIG] ORATS API token loaded (hardcoded, private mode)")
    print("[CONFIG] ORATS API token loaded (hardcoded, private mode)")
    base_url = "https://api.orats.io/datav2"
    probe_status = "DOWN"
    try:
        from app.core.orats.orats_client import probe_orats_live
        probe_orats_live("SPY")
        probe_status = "OK"
    except Exception as e:
        logger.warning("ORATS boot probe failed: %s", e)
    api_routes = _collect_api_routes(app)
    count = len(api_routes)
    logger.info("[ROUTES] registered=%s", count)
    print(f"[ROUTES] registered={count}")
    print("===== ORATS BOOT CHECK =====")
    print("Token present: True")
    print("Base URL:", base_url)
    print("Probe status:", probe_status)
    print("===========================")
    # Slack: log whether webhook is configured (do not log the URL)
    _slack_configured = bool((os.getenv("SLACK_WEBHOOK_URL") or "").strip())
    print("===== SLACK =====")
    print("Configured:", _slack_configured)
    if not _slack_configured:
        print("Set SLACK_WEBHOOK_URL in .env and restart to enable Slack alerts.")
    print("=================")

    # TTS (OpenAI): log whether text-to-speech is available (do not log the key)
    _openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    _tts_configured = bool(_openai_key)
    print("===== TTS (Text-to-Speech) =====")
    print("OPENAI_API_KEY configured:", _tts_configured)
    if not _tts_configured:
        print("Set OPENAI_API_KEY in chakraops/.env and restart to enable read-aloud on Strategy page.")
    print("=================================")

    # Phase 5: Clear stale run lock on startup (e.g. after crash)
    try:
        from app.core.eval.evaluation_store import clear_stale_run_lock
        clear_stale_run_lock()
    except Exception:
        pass

    # Start background scheduler for universe evaluation
    print("===== SCHEDULER STARTUP =====")
    print(f"Interval: {UNIVERSE_EVAL_MINUTES} minutes")
    print(f"Market open: {is_market_open()}")
    print(f"Market phase: {get_market_phase()}")
    start_evaluation_scheduler()
    print("Scheduler: STARTED")
    print("=============================")
    
    # Start nightly scheduler
    print("===== NIGHTLY SCHEDULER STARTUP =====")
    print(f"Enabled: {NIGHTLY_EVAL_ENABLED}")
    print(f"Time: {NIGHTLY_EVAL_TIME} {NIGHTLY_EVAL_TZ}")
    start_nightly_scheduler()
    nightly_status = get_nightly_scheduler_status()
    print(f"Running: {nightly_status['running']}")
    print(f"Next scheduled: {nightly_status.get('next_scheduled_at', 'N/A')}")
    print("=====================================")
    
    yield
    
    # Shutdown: stop the schedulers
    print("===== SCHEDULER SHUTDOWN =====")
    stop_evaluation_scheduler()
    print("Scheduler: STOPPED")
    stop_nightly_scheduler()
    print("Nightly: STOPPED")
    print("===============================")


app = FastAPI(title="ChakraOps API", version="0.1.0", lifespan=_lifespan)

# Phase 7: API key auth (when CHAKRAOPS_API_KEY is set). /health and /api/healthz are always public.
CHAKRAOPS_API_KEY = (os.getenv("CHAKRAOPS_API_KEY") or "").strip()
_PUBLIC_PATHS = frozenset({"/health", "/api/healthz"})


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require X-API-Key for all non-health routes when CHAKRAOPS_API_KEY is set."""
    path = request.url.path.rstrip("/") or request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)
    if not CHAKRAOPS_API_KEY:
        return await call_next(request)
    key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if key != CHAKRAOPS_API_KEY:
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid X-API-Key"},
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_dir() -> str:
    try:
        from app.core.settings import get_output_dir
        return get_output_dir()
    except Exception:
        return str(_repo_root() / "out")


@app.get("/api/ops/routes")
def api_ops_routes() -> list:
    """Route manifest: only /api/ routes. path, methods, name. For debugging 404s."""
    return _collect_api_routes(app)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Phase 7: Railway (and other) health checks. No auth required."""
    return {"ok": True, "status": "healthy"}


@app.get("/api/healthz")
def api_healthz() -> Dict[str, Any]:
    """Quick health check. Phase 10: prefer /api/market-status for full state. No auth when API key is set."""
    return {"ok": True}


@app.get("/api/market-status")
def api_market_status() -> Dict[str, Any]:
    """Phase 10: Market phase, last_market_check, last_evaluated_at, evaluation_attempted, evaluation_emitted, skip_reason."""
    status = read_market_status()
    phase = get_market_phase()
    return {
        "ok": True,
        "market_phase": phase,
        "last_market_check": status.get("last_market_check"),
        "last_evaluated_at": status.get("last_evaluated_at"),
        "evaluation_attempted": bool(status.get("evaluation_attempted", False)),
        "evaluation_emitted": bool(status.get("evaluation_emitted", False)),
        "skip_reason": status.get("skip_reason"),
    }


@app.get("/api/ops/status")
def api_ops_status() -> Dict[str, Any]:
    """Phase 12: last_run_at, next_run_at, cadence_minutes, symbols_evaluated, trades_found, blockers_summary, market_phase."""
    status = read_market_status()
    phase = get_market_phase()
    last_evaluated_at = status.get("last_evaluated_at")
    cadence_sec = get_eval_interval_seconds()
    cadence_minutes = cadence_sec // 60
    next_run_at = None
    if last_evaluated_at:
        try:
            last_ts = datetime.fromisoformat(last_evaluated_at.replace("Z", "+00:00")).timestamp()
            next_run_at = (datetime.fromtimestamp(last_ts + cadence_sec, tz=timezone.utc).isoformat())
        except (ValueError, TypeError):
            pass
    return {
        "last_run_at": last_evaluated_at,
        "next_run_at": next_run_at,
        "cadence_minutes": cadence_minutes,
        "last_run_reason": status.get("skip_reason"),
        "symbols_evaluated": status.get("symbols_evaluated", 0) if isinstance(status.get("symbols_evaluated"), int) else 0,
        "trades_found": status.get("trades_found", 0) if isinstance(status.get("trades_found"), int) else 0,
        "blockers_summary": status.get("blockers_summary") if isinstance(status.get("blockers_summary"), dict) else {},
        "market_phase": phase,
    }


@app.get("/api/ops/scheduler-status")
def api_ops_scheduler_status() -> Dict[str, Any]:
    """Get background scheduler status: running, interval, last run, next expected run."""
    status = get_scheduler_status()
    phase = get_market_phase()
    
    # Calculate next expected run
    next_expected_at = None
    if status["running"] and status["last_scheduled_eval_at"]:
        try:
            last_ts = datetime.fromisoformat(status["last_scheduled_eval_at"].replace("Z", "+00:00")).timestamp()
            next_ts = last_ts + (status["interval_minutes"] * 60)
            next_expected_at = datetime.fromtimestamp(next_ts, tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
    
    # Include nightly scheduler status
    nightly_status = get_nightly_scheduler_status()
    
    return {
        "scheduler_running": status["running"],
        "interval_minutes": status["interval_minutes"],
        "last_scheduled_eval_at": status["last_scheduled_eval_at"],
        "next_expected_at": next_expected_at,
        "market_open": status["market_open"],
        "market_phase": phase,
        "will_run_next": status["running"] and phase == "OPEN",
        "note": "Scheduler only triggers evaluations when market is OPEN",
        "nightly": nightly_status,
    }


@app.get("/api/ops/nightly-status")
def api_ops_nightly_status() -> Dict[str, Any]:
    """Get nightly evaluation scheduler status."""
    status = get_nightly_scheduler_status()
    return {
        "ok": True,
        **status,
        "note": f"Nightly evaluation runs at {status['eval_time']} {status['timezone']}",
    }


@app.get("/api/ops/market-regime")
def api_ops_market_regime() -> Dict[str, Any]:
    """Phase 7: Index-based market regime (RISK_ON, NEUTRAL, RISK_OFF). Persisted once per trading day."""
    try:
        from app.core.market.market_regime import get_market_regime
        snapshot = get_market_regime()
        return {
            "ok": True,
            "date": snapshot.date,
            "regime": snapshot.regime,
            "inputs": snapshot.inputs,
        }
    except Exception as e:
        logger.exception("Error getting market regime: %s", e)
        return {
            "ok": False,
            "date": None,
            "regime": None,
            "inputs": {},
            "error": str(e),
        }


# Snapshot configuration
STALE_THRESHOLD_SECONDS = 1800  # 30 minutes
REFRESH_CADENCE_SECONDS = 900   # 15 minutes


@app.get("/api/ops/snapshot")
def api_ops_snapshot() -> Dict[str, Any]:
    """System snapshot: summarizes current state WITHOUT triggering ORATS calls.
    
    NEVER THROWS - Always returns 200.
    SINGLE SOURCE OF TRUTH: Reads ONLY from persisted evaluation run.
    No live ORATS calls. Idempotent and deterministic.
    """
    from datetime import datetime, timezone
    
    # Initialize all variables with safe defaults
    now = datetime.now(timezone.utc)
    snapshot_time_utc = now.isoformat()
    warnings: list = []
    errors: list = []
    
    # Safe defaults for all fields
    universe_total = 0
    evaluated = 0
    eligible = 0
    shortlisted = 0
    holds = 0
    blocks = 0
    final_trade = None
    last_decision_id = None
    last_decision_time_utc = None
    decision_age_seconds = None
    decision_stale = False
    has_completed_run = False
    persisted_run = None
    market_phase = None
    run_mode = "DRY_RUN"
    status: Dict[str, Any] = {}
    orats_status = "UNKNOWN"
    orats_connected = False
    last_orats_success_at = None
    orats_status_reason = "Pending"
    evaluation_state = "IDLE"
    evaluation_state_reason = "No evaluation run yet"
    alerts_count = 0
    next_scheduled_refresh_utc = None
    evaluation_window = None
    
    try:
        # Market status (from persistence) - safe read
        try:
            status = read_market_status() or {}
            market_phase = get_market_phase()
            run_mode = status.get("source_mode", "DRY_RUN")
        except Exception:
            pass  # Keep defaults

        # Universe counts from CSV (does NOT call ORATS) - safe read
        try:
            from app.api.data_health import UNIVERSE_SYMBOLS
            universe_total = len(UNIVERSE_SYMBOLS) if UNIVERSE_SYMBOLS else 0
        except Exception:
            pass  # Keep default 0

        # SINGLE SOURCE OF TRUTH: Load from persisted evaluation run
        try:
            from app.core.eval.evaluation_store import build_latest_response
            persisted_run = build_latest_response()
            has_completed_run = persisted_run.get("has_completed_run", False) if persisted_run else False
            
            if has_completed_run and persisted_run:
                counts = persisted_run.get("counts") or {}
                evaluated = counts.get("evaluated", 0) or 0
                eligible = counts.get("eligible", 0) or 0
                shortlisted = counts.get("shortlisted", 0) or 0
                last_decision_id = persisted_run.get("run_id")
                last_decision_time_utc = persisted_run.get("completed_at")
                
                # Compute holds/blocks from symbols list
                symbols = persisted_run.get("symbols") or []
                holds = sum(1 for s in symbols if isinstance(s, dict) and s.get("verdict") == "HOLD")
                blocks = sum(1 for s in symbols if isinstance(s, dict) and s.get("verdict") == "BLOCKED")
                
                # Update universe_total from run if available
                if counts.get("total", 0) > 0:
                    universe_total = counts["total"]
                
                # Get final trade from top_candidates
                top_candidates = persisted_run.get("top_candidates") or []
                if top_candidates and isinstance(top_candidates, list) and len(top_candidates) > 0:
                    top = top_candidates[0]
                    if isinstance(top, dict):
                        final_trade = {
                            "symbol": top.get("symbol"),
                            "strategy": "CSP",
                            "direction": "SELL_TO_OPEN",
                            "confidence": top.get("confidence"),
                        }
                        ct_list = top.get("candidate_trades") or []
                        if ct_list and isinstance(ct_list, list) and len(ct_list) > 0:
                            final_trade["strategy"] = ct_list[0].get("strategy", "CSP")
        except Exception as e:
            logger.warning("[SNAPSHOT] Could not load persisted run: %s", e)

        # Calculate decision age
        eval_at = last_decision_time_utc or status.get("last_evaluated_at")
        if eval_at:
            try:
                eval_ts = datetime.fromisoformat(str(eval_at).replace("Z", "+00:00"))
                decision_age_seconds = int((now - eval_ts).total_seconds())
                if decision_age_seconds > STALE_THRESHOLD_SECONDS:
                    decision_stale = True
            except (ValueError, TypeError):
                pass

        # Calculate next scheduled refresh
        try:
            scheduler_interval_sec = UNIVERSE_EVAL_MINUTES * 60
            next_refresh_ts = now.timestamp() + scheduler_interval_sec
            if eval_at:
                try:
                    eval_ts = datetime.fromisoformat(str(eval_at).replace("Z", "+00:00"))
                    next_refresh_ts = eval_ts.timestamp() + scheduler_interval_sec
                    if next_refresh_ts < now.timestamp():
                        next_refresh_ts = now.timestamp() + scheduler_interval_sec
                except (ValueError, TypeError):
                    pass
            next_scheduled_refresh_utc = datetime.fromtimestamp(next_refresh_ts, tz=timezone.utc).isoformat()
        except Exception:
            pass

        # ORATS status - derive from persisted run, NO live calls
        if has_completed_run:
            orats_connected = True
            orats_status = "OK"
            orats_status_reason = "OK - data available from completed evaluation"
        else:
            try:
                from app.api.data_health import _DATA_STATUS, _LAST_SUCCESS_AT
                orats_status = _DATA_STATUS or "UNKNOWN"
                last_orats_success_at = _LAST_SUCCESS_AT
                orats_connected = orats_status == "OK"
                if orats_status == "OK":
                    orats_status_reason = f"OK - last call at {_LAST_SUCCESS_AT}" if _LAST_SUCCESS_AT else "OK"
                elif orats_status == "UNKNOWN":
                    orats_status_reason = "Pending - awaiting first evaluation"
                else:
                    orats_status_reason = f"{orats_status}"
            except Exception:
                orats_status_reason = "Pending - awaiting first evaluation"

        # Determine evaluation_state
        try:
            from app.core.eval.universe_evaluator import get_evaluation_state
            eval_state = get_evaluation_state() or {}
            if eval_state.get("evaluation_state") == "RUNNING":
                evaluation_state = "RUNNING"
                evaluation_state_reason = _clean_encoding(eval_state.get("evaluation_state_reason", "In progress"))
        except Exception:
            pass

        # Check job-based state
        if evaluation_state == "IDLE":
            try:
                running_jobs = [j for j in _eval_jobs.values() if isinstance(j, dict) and j.get("state") == "running"]
                if running_jobs:
                    evaluation_state = "RUNNING"
                    evaluation_state_reason = "Evaluation in progress"
            except Exception:
                pass

        # Derive from persisted run
        if evaluation_state == "IDLE" and has_completed_run:
            evaluation_state = "COMPLETED"
            evaluation_state_reason = f"Completed (manual run) - {evaluated} evaluated, {eligible} eligible"
            alerts_count = (persisted_run.get("alerts_count", 0) or 0) if persisted_run else 0

        # Build evaluation window
        if eval_at:
            try:
                eval_ts = datetime.fromisoformat(str(eval_at).replace("Z", "+00:00"))
                evaluation_window = {
                    "date": eval_ts.strftime("%Y-%m-%d"),
                    "asof_time_utc": eval_ts.isoformat(),
                }
            except (ValueError, TypeError):
                pass

    except Exception as e:
        # Catch-all - snapshot must NEVER throw
        logger.exception("[SNAPSHOT] Unexpected error: %s", e)
        errors.append({"code": "SNAPSHOT_ERROR", "message": str(e)})

    # Determine snapshot phase
    snapshot_phase = "IDLE"
    if evaluation_state == "RUNNING":
        snapshot_phase = "EVALUATING"
    elif decision_stale:
        snapshot_phase = "STALE"
    elif has_completed_run:
        snapshot_phase = "COMPLETE"

    # Explicit boolean flags
    has_decision_artifact = has_completed_run
    has_evaluation_run = has_completed_run
    data_stale = decision_stale

    # Build pipeline_steps - derive from PERSISTED RUN only
    universe_load_ok = universe_total > 0
    market_check_ok = market_phase is not None
    orats_check_ok = orats_connected or has_completed_run
    eval_run_ok = has_completed_run and evaluated > 0
    decision_emit_ok = has_completed_run

    run_id_short = (last_decision_id[-8:] if last_decision_id and len(last_decision_id) >= 8 else last_decision_id) or "?"
    
    pipeline_steps = [
        {
            "step": "Universe Load",
            "status": "OK" if universe_load_ok else "PENDING",
            "detail": f"{universe_total} symbols loaded" if universe_load_ok else "No symbols loaded",
            "last_transition_time": None,
            "blocking": not universe_load_ok,
            "explanation": "Universe defines symbols to evaluate"
        },
        {
            "step": "Market Status Check",
            "status": "OK",
            "detail": f"Market phase: {market_phase or 'CLOSED'}",
            "last_transition_time": status.get("last_market_check") if status else None,
            "blocking": False,
            "explanation": "Market status for context"
        },
        {
            "step": "ORATS Connectivity",
            "status": "OK" if orats_check_ok else "PENDING",
            "detail": orats_status_reason if orats_check_ok else "Awaiting first evaluation",
            "last_transition_time": last_orats_success_at or last_decision_time_utc,
            "blocking": False,
            "explanation": "ORATS provides options data"
        },
        {
            "step": "Evaluation Run",
            "status": "OK" if eval_run_ok else ("RUNNING" if evaluation_state == "RUNNING" else "PENDING"),
            "detail": f"Run {run_id_short}: {evaluated} evaluated, {eligible} eligible, {holds} holds" if eval_run_ok else ("In progress..." if evaluation_state == "RUNNING" else "Click 'Run evaluation now'"),
            "last_transition_time": last_decision_time_utc,
            "blocking": False,
            "explanation": "Evaluation scans universe for trades"
        },
        {
            "step": "Decision Emit",
            "status": "OK" if decision_emit_ok else "PENDING",
            "detail": f"Trade: {final_trade['symbol']} ({final_trade.get('strategy', 'CSP')})" if (decision_emit_ok and final_trade and eligible > 0) else ("No eligible candidates" if decision_emit_ok else "Awaiting evaluation"),
            "last_transition_time": last_decision_time_utc,
            "blocking": False,
            "explanation": "Emits recommended trade"
        },
    ]
    # Return snapshot - ALWAYS 200, NEVER throws
    return {
        # Snapshot contract
        "snapshot_ok": has_completed_run or evaluation_state == "RUNNING",
        "has_run": has_completed_run,
        "reason": None if has_completed_run else "NO_LATEST_RUN",
        
        # Core identification
        "snapshot_id": snapshot_time_utc,
        "snapshot_time_utc": snapshot_time_utc,
        "snapshot_age_seconds": 0,
        
        # Lifecycle
        "snapshot_phase": snapshot_phase,
        "stale_threshold_seconds": STALE_THRESHOLD_SECONDS,
        "next_scheduled_refresh_utc": next_scheduled_refresh_utc,
        
        # Evaluation state
        "evaluation_state": evaluation_state,
        "evaluation_state_reason": evaluation_state_reason,
        
        # Boolean flags for UI
        "has_evaluation_run": has_evaluation_run,
        "has_decision_artifact": has_decision_artifact,
        "orats_connected": orats_connected,
        "data_stale": data_stale,
        
        # Run configuration
        "run_mode": run_mode,
        
        # Market status
        "market_status": {
            "open": market_phase == "OPEN",
            "phase": market_phase or "CLOSED",
            "status": "OPEN" if market_phase == "OPEN" else "CLOSED",
            "last_market_check": status.get("last_market_check") if status else None,
            "last_evaluated_at": status.get("last_evaluated_at") if status else None,
            "evaluation_attempted": status.get("evaluation_attempted", False) if status else False,
            "evaluation_emitted": status.get("evaluation_emitted", False) if status else False,
            "skip_reason": status.get("skip_reason") if status else None,
        },
        
        # Evaluation window
        "evaluation_window": evaluation_window,
        
        # Universe counts (from PERSISTED RUN)
        "universe": {
            "total": universe_total,
            "evaluated": evaluated,
            "eligible": eligible,
            "shortlisted": shortlisted,
            "holds": holds,
            "blocked": blocks,
        },
        
        # Counts alias for compatibility
        "universe_counts": {
            "total": universe_total,
            "evaluated": evaluated,
            "eligible": eligible,
            "shortlisted": shortlisted,
        },
        "alerts_count": alerts_count,
        "last_alerts_generated_at": last_decision_time_utc,
        
        # Decision state
        "snapshot_state": {
            "last_decision_id": last_decision_id,
            "last_decision_time_utc": last_decision_time_utc,
            "decision_age_seconds": decision_age_seconds,
            "decision_source": "persisted_run" if has_completed_run else "none",
            "decision_stale": decision_stale,
        },
        
        # Trade result
        "final_trade": final_trade,
        
        # ORATS status (no live calls)
        "orats_status": orats_status,
        "orats_status_reason": orats_status_reason,
        "last_orats_success_at": last_orats_success_at,
        
        # Pipeline steps for diagnostics
        "pipeline_steps": pipeline_steps,
        
        # Issues
        "warnings": warnings,
        "errors": errors,
        
        # Scheduler status
        "scheduler": get_scheduler_status(),
    }


@app.get("/api/ops/data-health")
def api_ops_data_health() -> Dict[str, Any]:
    """ORATS data health: sticky status (UNKNOWN/OK/WARN/DOWN). Persisted; probe only when UNKNOWN. Phase 8B."""
    from app.api.data_health import get_data_health
    state = get_data_health()
    return {
        "provider": state.get("provider", "ORATS"),
        "status": state.get("status", "UNKNOWN"),
        "last_success_at": state.get("last_success_at"),
        "last_attempt_at": state.get("last_attempt_at"),
        "last_error_at": state.get("last_error_at"),
        "last_error_reason": state.get("last_error_reason"),
        "avg_latency_seconds": state.get("avg_latency_seconds"),
        "entitlement": state.get("entitlement", "UNKNOWN"),
        "sample_symbol": state.get("sample_symbol", "SPY"),
        "evaluation_window_minutes": state.get("evaluation_window_minutes"),
    }


@app.post("/api/ops/refresh-live-data")
def api_ops_refresh_live_data() -> Dict[str, Any]:
    """Call probe_orats_live(SPY) and return raw result. 503 on failure."""
    from app.core.orats.orats_client import probe_orats_live, OratsUnavailableError
    try:
        result = probe_orats_live("SPY")
        return result
    except OratsUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail={"provider": "ORATS", "reason": str(e), "http_status": getattr(e, "http_status", 0)},
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail={"provider": "ORATS", "reason": str(e)})


@app.post("/api/ops/reset-local-state")
def api_ops_reset_local_state() -> Dict[str, Any]:
    """DEV ONLY: Reset local cached state (market_status.json, cached ORATS state).
    
    Protected by OPS_ENABLE_RESET=true env var. Returns 404 in production.
    Does NOT delete universe.csv or decision artifacts.
    """
    from datetime import datetime, timezone
    
    # Check env flag - must be explicitly enabled
    if os.getenv("OPS_ENABLE_RESET", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")
    
    cleared: list = []
    errors: list = []
    
    # Reset market_status.json
    try:
        status_path = Path(_output_dir()) / "market_status.json"
        if status_path.exists():
            status_path.unlink()
            cleared.append("market_status.json")
    except Exception as e:
        errors.append(f"market_status.json: {e}")
    
    # Reset cached ORATS state (in-memory + persisted Phase 8B file)
    try:
        from app.api import data_health
        data_health._DATA_STATUS = "UNKNOWN"
        data_health._LAST_SUCCESS_AT = None
        data_health._LAST_ATTEMPT_AT = None
        data_health._LAST_ERROR_AT = None
        data_health._LAST_ERROR_REASON = None
        data_health._AVG_LATENCY_SECONDS = None
        data_health._LATENCY_SAMPLES = []
        data_health._ENTITLEMENT = "UNKNOWN"
        path = data_health._data_health_state_path()
        if path.exists():
            path.unlink()
            cleared.append("data_health_state.json")
        cleared.append("orats_cached_state")
    except Exception as e:
        errors.append(f"orats_cached_state: {e}")
    
    # Clear eval job cache
    global _eval_jobs, _last_eval_ts
    with _jobs_lock:
        job_count = len(_eval_jobs)
        _eval_jobs = {}
        _last_eval_ts = 0
        if job_count > 0:
            cleared.append(f"eval_jobs ({job_count})")
    
    return {
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "cleared": cleared,
        "errors": errors,
        "note": "Decision artifacts and universe.csv were NOT deleted",
    }


@app.get("/api/view/daily-overview")
def api_view_daily_overview() -> Dict[str, Any]:
    """Daily overview from decision_latest.json. Includes fetched_at (ISO) for UI timestamps."""
    from datetime import datetime, timezone
    fetched_at = datetime.now(timezone.utc).isoformat()
    artifact = load_decision_artifact()
    if not artifact:
        out = build_daily_overview_from_artifact({
            "daily_trust_report": {},
            "metadata": {},
            "decision_snapshot": {},
        })
        out["fetched_at"] = fetched_at
        return JSONResponse(status_code=200, content=out)
    out = build_daily_overview_from_artifact(artifact)
    out["fetched_at"] = fetched_at
    return out


@app.get("/api/view/positions")
def api_view_positions() -> list:
    """Positions from persistence."""
    return get_positions_for_api()


@app.get("/api/view/alerts")
def api_view_alerts() -> Dict[str, Any]:
    """Alerts from persistence + daily overview."""
    artifact = load_decision_artifact()
    daily = build_daily_overview_from_artifact(artifact or {}) if artifact else None
    return get_alerts_for_api(daily_overview=daily)


@app.get("/api/view/decision-history")
def api_view_decision_history() -> list:
    """Decision history (latest from artifact)."""
    return get_decision_history_for_api()


@app.get("/api/view/trade-plan")
def api_view_trade_plan() -> Dict[str, Any]:
    """Optional: trade plan from latest decision. Always 200; returns null/empty if none."""
    artifact = load_decision_artifact()
    if not artifact:
        return {"trade_plan": None, "fetched_at": None}
    from datetime import datetime, timezone
    snapshot = artifact.get("decision_snapshot") or {}
    proposal = snapshot.get("trade_proposal")
    return {
        "trade_plan": proposal,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/view/universe")
def api_view_universe() -> Dict[str, Any]:
    """Universe: best-effort from persistence/ORATS. Never 503  -  return empty symbols and log on failure (decoupled from ORATS)."""
    from datetime import datetime, timezone
    try:
        from app.api.data_health import fetch_universe_from_orats
        result = fetch_universe_from_orats()
        if result["all_failed"]:
            logger.warning("[UNIVERSE] ORATS returned no data for any symbol; returning empty. excluded=%s", result.get("excluded"))
            return {"symbols": [], "excluded": result.get("excluded", []), "updated_at": datetime.now(timezone.utc).isoformat(), "error": None}
        return {
            "symbols": result["symbols"],
            "excluded": result.get("excluded", []),
            "updated_at": result["updated_at"],
            "error": None,
        }
    except Exception as e:
        logger.warning("[UNIVERSE] Universe load failed (ORATS/persistence): %s; returning empty.", e, exc_info=False)
        return {"symbols": [], "excluded": [], "updated_at": datetime.now(timezone.utc).isoformat(), "error": None}


def _infer_liquidity_tier(notes: str) -> Optional[str]:
    """Infer liquidity tier from notes if present (e.g. 'A', 'B')."""
    if not notes:
        return None
    s = notes.strip().upper()
    if len(s) == 1 and s in ("A", "B", "C", "D"):
        return s
    for prefix in ("tier ", "tier:", "liquidity "):
        if prefix in s.lower():
            rest = s.split(prefix, 1)[-1].strip()
            if rest and rest[0] in ("A", "B", "C", "D"):
                return rest[0]
    return None


@app.post("/api/ops/evaluate")
def api_ops_evaluate(
    request: Request,
    x_trigger_token: Optional[str] = Header(None, alias="X-Trigger-Token"),
) -> Dict[str, Any]:
    """Phase 10: Trigger DRY_RUN evaluation. Cooldown 5 min. Optional X-Trigger-Token from env EVALUATE_TRIGGER_TOKEN."""
    global _last_eval_ts, _eval_jobs
    token = os.getenv("EVALUATE_TRIGGER_TOKEN")
    if token and x_trigger_token != token:
        raise HTTPException(status_code=403, detail="Invalid or missing trigger token")
    now = time.time()
    with _jobs_lock:
        remaining = EVAL_COOLDOWN_SEC - (now - _last_eval_ts)
        if remaining > 0:
            return {
                "job_id": None,
                "accepted": False,
                "cooldown_seconds_remaining": int(remaining),
            }
        job_id = str(uuid.uuid4())
        _eval_jobs[job_id] = {"state": "queued", "started_at": None, "finished_at": None, "error": None}
        _last_eval_ts = now

    def run_eval():
        global _eval_jobs
        with _jobs_lock:
            _eval_jobs[job_id]["state"] = "running"
            _eval_jobs[job_id]["started_at"] = time.time()
        try:
            out_dir = _output_dir()
            result = subprocess.run(
                [sys.executable, "-m", "scripts.run_and_save", "--output-dir", out_dir],
                cwd=str(_repo_root()),
                capture_output=True,
                text=True,
                timeout=120,
            )
            with _jobs_lock:
                _eval_jobs[job_id]["state"] = "done" if result.returncode == 0 else "failed"
                _eval_jobs[job_id]["finished_at"] = time.time()
                if result.returncode != 0:
                    _eval_jobs[job_id]["error"] = result.stderr[:500] if result.stderr else "Non-zero exit"
        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _eval_jobs[job_id]["state"] = "failed"
                _eval_jobs[job_id]["finished_at"] = time.time()
                _eval_jobs[job_id]["error"] = "Timeout (120s)"
        except Exception as e:
            with _jobs_lock:
                _eval_jobs[job_id]["state"] = "failed"
                _eval_jobs[job_id]["finished_at"] = time.time()
                _eval_jobs[job_id]["error"] = str(e)[:500]

    threading.Thread(target=run_eval, daemon=True).start()
    return {"job_id": job_id, "accepted": True}


@app.get("/api/ops/evaluate/{job_id}")
def api_ops_evaluate_status(job_id: str) -> Dict[str, Any]:
    """Phase 10/12: Job status (queued|running|done|failed|not_found). Always 200; unknown job_id returns state=not_found."""
    with _jobs_lock:
        job = _eval_jobs.get(job_id)
    if not job:
        return {
            "state": "not_found",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
    return {
        "state": job["state"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
    }


@app.get("/api/view/symbol-diagnostics")
def api_view_symbol_diagnostics(symbol: str = Query(..., min_length=1, max_length=12)) -> Dict[str, Any]:
    """Symbol diagnostics with FULL EXPLAINABILITY for ANY valid ticker.
    
    Returns comprehensive data including:
    - Stock snapshot (price, bid, ask, volume, trend)
    - Eligibility verdict with primary reason
    - Gates status (PASS/FAIL with reasons)
    - Regime and risk assessment
    - Liquidity analysis
    - Options and Greeks summary
    - Candidate trades (if eligible)
    
    503 if ORATS fails for this symbol.
    """
    from datetime import datetime, timezone
    from app.core.orats.orats_client import get_orats_live_summaries, OratsUnavailableError
    sym = symbol.strip().upper()
    t0 = time.perf_counter()
    try:
        orats_data = get_orats_live_summaries(sym, timeout_sec=15.0)
    except OratsUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "provider": "ORATS",
                "reason": str(e),
                "endpoint": getattr(e, "endpoint", "") or "summaries",
                "symbol": getattr(e, "symbol", "") or sym,
                "http_status": e.http_status,
            },
        )
    elapsed = time.perf_counter() - t0
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not orats_data or (isinstance(orats_data, list) and len(orats_data) == 0):
        raise HTTPException(
            status_code=503,
            detail={
                "provider": "ORATS",
                "reason": "ORATS returned no data for symbol",
                "symbol": sym,
            },
        )
    
    # Extract stock data from ORATS response
    first = orats_data[0] if isinstance(orats_data, list) and orats_data else {}
    stock_price = None
    for key in ("stockPrice", "closePrice", "close", "last", "price"):
        if first.get(key) is not None:
            try:
                stock_price = float(first[key])
                break
            except (TypeError, ValueError):
                pass
    
    # Build stock snapshot
    # NOTE: ORATS /live/summaries is a VOLATILITY endpoint, NOT an equity quote endpoint.
    # It does NOT provide bid/ask/volume/avgVolume - those would come from an equity data feed.
    stock = {
        "price": stock_price,
        "bid": None,  # NOT in ORATS summaries
        "ask": None,  # NOT in ORATS summaries
        "volume": None,  # NOT in ORATS summaries
        "avg_volume": None,  # NOT in ORATS summaries
        "trend": _compute_trend(first),
    }
    
    # Initialize result with full explainability structure
    result = {
        "symbol": sym,
        "snapshot_time": fetched_at,
        "fetched_at": fetched_at,
        "data_latency_seconds": round(elapsed, 3),
        
        # Stock snapshot
        "stock": stock,
        
        # Eligibility (will be filled)
        "eligibility": {
            "verdict": "UNKNOWN",
            "primary_reason": "Not yet evaluated",
            "confidence_score": None,
        },
        
        # Legacy fields for backward compatibility
        "in_universe": False,
        "universe_reason": None,
        "status": None,
        "recommendation": "UNKNOWN",
        
        # Gates
        "gates": [],
        "blockers": [],
        
        # Regime assessment
        "regime": {
            "market_regime": None,
            "allowed": True,
            "reason": "No regime data available",
        },
        
        # Risk assessment
        "risk": {
            "posture": None,
            "allowed": True,
            "reason": "No risk data available",
        },
        
        # Legacy market object
        "market": {"regime": None, "risk_posture": None},
        
        # Liquidity
        "liquidity": {
            "stock_liquidity_ok": True,
            "option_liquidity_ok": True,
            "reason": "Liquidity not assessed",
        },
        
        # Earnings
        "earnings": {
            "next_date": None,
            "days_to_earnings": None,
            "blocked": False,
            "reason": "No earnings data",
        },
        
        # Options
        "options": {
            "has_options": True,
            "chain_ok": True,
            "expirations_count": len(orats_data) if isinstance(orats_data, list) else None,
            "contracts_count": None,
            "underlying_price": stock_price,
        },
        
        # Greeks summary
        # NOTE: ORATS /live/summaries does NOT provide ivRank directly.
        # We compute it from iv30d/iv1y ratio (same as staged_evaluator).
        "greeks_summary": {
            "iv_rank": _compute_iv_rank(first),
            "iv_percentile": _safe_float(first.get("ivPct") or first.get("iv30Pct")),
            "delta_target_range": "0.20-0.35 for CSP",
            "theta_bias": "Favor high theta / low DTE",
        },
        
        # Candidate trades
        "candidate_trades": [],
        
        # Notes
        "notes": [],
    }
    
    # Check universe membership
    in_universe = False
    try:
        from app.api.data_health import UNIVERSE_SYMBOLS
        in_universe = sym in UNIVERSE_SYMBOLS
        if in_universe:
            result["in_universe"] = True
            result["universe_reason"] = "Symbol is in evaluation universe (config/universe.csv)"
        else:
            result["status"] = "OUT_OF_SCOPE"
            result["in_universe"] = False
            result["universe_reason"] = "Symbol not in evaluation universe"
            result["eligibility"]["verdict"] = "BLOCKED"
            result["eligibility"]["primary_reason"] = "Not in evaluation universe - add to config/universe.csv to include"
            # Add explicit gate FAIL for clarity
            result["gates"].insert(0, {
                "name": "Universe Membership",
                "status": "FAIL",
                "pass": False,
                "reason": "Symbol not in config/universe.csv",
                "code": "NOT_IN_UNIVERSE",
            })
            result["blockers"].append({
                "code": "NOT_IN_UNIVERSE",
                "message": "Symbol not in evaluation universe",
                "severity": "info",
                "impact": "Symbol will not be evaluated for trading",
            })
            result["recommendation"] = "NOT_ELIGIBLE"
            result["notes"].append("Add symbol to config/universe.csv to include in evaluation")
    except Exception as e:
        result["notes"].append(f"Universe check failed: {e}")
    
    # SINGLE SOURCE OF TRUTH: Check persisted evaluation run FIRST
    # If symbol was evaluated, use that as the canonical verdict/reason/bands
    persisted_symbol_data = None
    persisted_run_id = None
    persisted_evaluated_at = None
    try:
        from app.core.eval.evaluation_store import load_latest_run
        latest = load_latest_run()
        if latest and getattr(latest, "symbols", None):
            persisted_run_id = getattr(latest, "run_id", None)
            persisted_evaluated_at = getattr(latest, "completed_at", None)
            for s in latest.symbols:
                if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym:
                    persisted_symbol_data = s
                    break
    except Exception as e:
        result["notes"].append(f"Could not load persisted run: {e}")
    
    # Fill from decision artifact (for regime/risk context)
    try:
        artifact = load_decision_artifact()
        _fill_diagnostics_from_artifact_extended(result, sym, artifact)
    except Exception as e:
        result["notes"].append(f"Diagnostics partial: {e}")
    
    # If we have persisted evaluation data, use it as the SINGLE SOURCE OF TRUTH
    if persisted_symbol_data:
        result["eligibility"]["verdict"] = persisted_symbol_data.get("verdict", "UNKNOWN")
        result["eligibility"]["primary_reason"] = persisted_symbol_data.get("primary_reason", "")
        result["eligibility"]["confidence_score"] = persisted_symbol_data.get("confidence")
        result["eligibility"]["score"] = persisted_symbol_data.get("score", 0)
        if persisted_symbol_data.get("rationale"):
            result["eligibility"]["rationale"] = persisted_symbol_data["rationale"]
        if "position_open" in persisted_symbol_data:
            result["eligibility"]["position_open"] = persisted_symbol_data["position_open"]
        if "position_reason" in persisted_symbol_data:
            result["eligibility"]["position_reason"] = persisted_symbol_data["position_reason"]
        if persisted_symbol_data.get("capital_hint"):
            result["eligibility"]["capital_hint"] = persisted_symbol_data["capital_hint"]
        # Phase 3: Score breakdown and rank reasons (Ticker page explainability)
        if persisted_symbol_data.get("score_breakdown") is not None:
            result["eligibility"]["score_breakdown"] = persisted_symbol_data["score_breakdown"]
        if persisted_symbol_data.get("rank_reasons") is not None:
            result["eligibility"]["rank_reasons"] = persisted_symbol_data["rank_reasons"]
        if persisted_symbol_data.get("csp_notional") is not None:
            result["eligibility"]["csp_notional"] = persisted_symbol_data["csp_notional"]
        if persisted_symbol_data.get("notional_pct") is not None:
            result["eligibility"]["notional_pct"] = persisted_symbol_data["notional_pct"]
        if persisted_symbol_data.get("band_reason") is not None:
            result["eligibility"]["band_reason"] = persisted_symbol_data["band_reason"]
        if persisted_symbol_data.get("verdict_reason_code"):
            result["eligibility"]["verdict_reason_code"] = persisted_symbol_data["verdict_reason_code"]
        if persisted_symbol_data.get("data_incomplete_type"):
            result["eligibility"]["data_incomplete_type"] = persisted_symbol_data["data_incomplete_type"]
        # Copy gates and blockers from persisted run
        if persisted_symbol_data.get("gates"):
            result["gates"] = persisted_symbol_data["gates"]
        if persisted_symbol_data.get("blockers"):
            result["blockers"] = persisted_symbol_data["blockers"]
        if persisted_symbol_data.get("candidate_trades"):
            result["candidate_trades"] = persisted_symbol_data["candidate_trades"]
        # Mark that this came from persisted run
        result["eligibility"]["from_persisted_run"] = True
        result["eligibility"]["run_id"] = persisted_run_id
        result["eligibility"]["evaluated_at"] = persisted_evaluated_at
        result["recommendation"] = persisted_symbol_data.get("verdict", "UNKNOWN")
        result["notes"].append(f"Verdict from persisted run {persisted_run_id or 'unknown'}")
    else:
        # No persisted data - compute verdict (fallback for non-evaluated symbols)
        _compute_eligibility_verdict(result)
        result["eligibility"]["from_persisted_run"] = False
        result["notes"].append("Symbol not in latest evaluation run - computed independently")
    
    # Generate candidate trades if eligible and none provided from persisted run
    if result["eligibility"]["verdict"] == "ELIGIBLE" and stock_price and not result["candidate_trades"]:
        _generate_candidate_trades(result, stock_price, first)
    
    return result


def _safe_float(val) -> float | None:
    """Safely convert to float, return None if not possible."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _compute_iv_rank(orats_row: dict) -> float | None:
    """
    Compute IV rank from ORATS summaries data.

    ORATS /live/summaries does NOT provide ivRank directly. We compute it
    from the ratio of 30-day IV to 1-year IV:
      - iv30d / iv1y ratio, scaled to 0-100 range
      - 50 means iv30d == iv1y (current IV at 1-year average)
      - <50 means IV is below 1-year average
      - >50 means IV is above 1-year average

    Returns None if iv30d or iv1y are missing/invalid.
    """
    iv30d = _safe_float(orats_row.get("iv30d"))
    iv1y = _safe_float(orats_row.get("iv1y"))
    if iv30d is None or iv1y is None or iv1y <= 0:
        return None
    iv_ratio = iv30d / iv1y
    return min(100.0, max(0.0, iv_ratio * 50.0))


def _safe_int(val) -> int | None:
    """Safely convert to int, return None if not possible."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _compute_trend(data: dict) -> str:
    """Compute trend from ORATS data."""
    try:
        close = _safe_float(data.get("close") or data.get("stockPrice"))
        prev_close = _safe_float(data.get("prevClose") or data.get("previousClose"))
        if close and prev_close:
            if close > prev_close * 1.005:
                return "UP"
            elif close < prev_close * 0.995:
                return "DOWN"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def _fill_diagnostics_from_artifact_extended(result: Dict[str, Any], sym: str, artifact: Optional[Dict[str, Any]]) -> None:
    """Fill market/regime, risk, and gates from decision artifact with full explainability."""
    if not artifact:
        result["regime"]["reason"] = "No evaluation artifact available  -  run evaluation first"
        result["risk"]["reason"] = "No evaluation artifact available  -  run evaluation first"
        return
    
    meta = artifact.get("metadata") or {}
    regime = meta.get("regime")
    risk_posture = meta.get("risk_posture")
    
    # Regime
    result["regime"]["market_regime"] = regime
    result["market"]["regime"] = regime
    if regime:
        regime_allowed = regime in ["BULLISH", "NEUTRAL", "RANGE_BOUND"]
        result["regime"]["allowed"] = regime_allowed
        result["regime"]["reason"] = f"Regime is {regime}" + ("  -  trading allowed" if regime_allowed else "  -  trading restricted")
        if not regime_allowed:
            result["gates"].append({
                "name": "regime_check",
                "status": "FAIL",
                "pass": False,
                "reason": f"Market regime {regime} does not allow new trades",
            })
    
    # Risk
    result["risk"]["posture"] = risk_posture
    result["market"]["risk_posture"] = risk_posture
    if risk_posture:
        risk_allowed = risk_posture in ["NORMAL", "AGGRESSIVE"]
        result["risk"]["allowed"] = risk_allowed
        result["risk"]["reason"] = f"Risk posture is {risk_posture}" + ("  -  trading allowed" if risk_allowed else "  -  reduced exposure")
        if not risk_allowed:
            result["gates"].append({
                "name": "risk_check",
                "status": "FAIL",
                "pass": False,
                "reason": f"Risk posture {risk_posture} restricts new trades",
            })
    
    # Check exclusions
    snapshot = artifact.get("decision_snapshot") or {}
    exclusions = snapshot.get("exclusions") or []
    for ex in exclusions:
        if isinstance(ex, dict) and (ex.get("symbol") or "").upper() == sym:
            code = ex.get("code", "exclusion")
            message = ex.get("message", ex.get("reason", ""))
            result["gates"].append({
                "name": code,
                "status": "FAIL",
                "pass": False,
                "reason": message,
                "code": code,
            })
            result["blockers"].append({
                "code": code,
                "message": message,
                "severity": ex.get("severity", "warning"),
                "impact": "Symbol excluded from trade selection",
            })
    
    # Check if symbol was evaluated
    evaluated_symbols = snapshot.get("evaluated_symbols") or []
    if sym in evaluated_symbols:
        result["gates"].append({
            "name": "evaluated",
            "status": "PASS",
            "pass": True,
            "reason": "Symbol was evaluated in last run",
        })
    
    # Add default pass gate if no gates
    if not result["gates"]:
        result["gates"].append({
            "name": "no_exclusion",
            "status": "PASS",
            "pass": True,
            "reason": "Symbol not in exclusion list",
        })


def _compute_eligibility_verdict(result: Dict[str, Any]) -> None:
    """Compute final eligibility verdict based on all checks."""
    # Already blocked for not in universe
    if result["eligibility"]["verdict"] == "BLOCKED":
        return
    
    failed_gates = [g for g in result["gates"] if not g.get("pass", True)]
    blockers = result.get("blockers", [])
    
    if failed_gates:
        result["eligibility"]["verdict"] = "BLOCKED"
        result["eligibility"]["primary_reason"] = failed_gates[0].get("reason", "Failed gate check")
        result["recommendation"] = "NOT_ELIGIBLE"
    elif blockers:
        result["eligibility"]["verdict"] = "HOLD"
        result["eligibility"]["primary_reason"] = blockers[0].get("message", "Has blockers")
        result["recommendation"] = "NOT_ELIGIBLE"
    elif not result["regime"].get("allowed", True):
        result["eligibility"]["verdict"] = "HOLD"
        result["eligibility"]["primary_reason"] = "Market regime restricts trading"
        result["recommendation"] = "NOT_ELIGIBLE"
    elif not result["risk"].get("allowed", True):
        result["eligibility"]["verdict"] = "HOLD"
        result["eligibility"]["primary_reason"] = "Risk posture restricts trading"
        result["recommendation"] = "NOT_ELIGIBLE"
    else:
        result["eligibility"]["verdict"] = "ELIGIBLE"
        result["eligibility"]["primary_reason"] = "All checks passed  -  eligible for trade selection"
        result["eligibility"]["confidence_score"] = 0.8 if result["in_universe"] else 0.5
        result["recommendation"] = "ELIGIBLE"


def _generate_candidate_trades(result: Dict[str, Any], stock_price: float, orats_data: dict) -> None:
    """Generate candidate trade ideas based on current data."""
    iv_rank = result["greeks_summary"].get("iv_rank")
    
    # CSP candidate (Cash Secured Put)
    strike_csp = round(stock_price * 0.85, 2)  # 15% OTM
    result["candidate_trades"].append({
        "strategy": "CSP",
        "description": "Cash Secured Put",
        "expiry": "30-45 DTE",
        "strike": strike_csp,
        "delta": -0.25,
        "credit_estimate": round(stock_price * 0.015, 2),  # ~1.5% of stock price
        "max_loss": strike_csp * 100,
        "why_this_trade": f"Sell put at ${strike_csp} (15% below current). Collect premium while willing to own at discount.",
    })
    
    # CC candidate (Covered Call) if holding stock
    strike_cc = round(stock_price * 1.10, 2)  # 10% OTM
    result["candidate_trades"].append({
        "strategy": "CC",
        "description": "Covered Call",
        "expiry": "30-45 DTE",
        "strike": strike_cc,
        "delta": 0.30,
        "credit_estimate": round(stock_price * 0.01, 2),  # ~1% of stock price
        "max_loss": None,  # No additional loss beyond stock ownership
        "why_this_trade": f"Sell call at ${strike_cc} (10% above current) against existing shares. Generate income.",
    })
    
    # HOLD if IV is low
    if iv_rank is not None and iv_rank < 25:
        result["candidate_trades"].append({
            "strategy": "HOLD",
            "description": "Wait for higher IV",
            "expiry": None,
            "strike": None,
            "delta": None,
            "credit_estimate": None,
            "max_loss": None,
            "why_this_trade": f"IV Rank is {iv_rank}% - below 25% threshold. Wait for better premium environment.",
        })


# ============================================================================
# UNIVERSE EVALUATION ENDPOINTS
# ============================================================================

@app.post("/api/ops/evaluate-now")
def api_ops_evaluate_now() -> Dict[str, Any]:
    """
    Run staged universe evaluation synchronously with persistence.
    Staged evaluation is the single source of truth; no legacy fallback.
    On staged failure: persist FAILED run, return HTTP 500.
    """
    from datetime import datetime, timezone
    try:
        from app.api.data_health import UNIVERSE_SYMBOLS
        from app.core.eval.universe_evaluator import run_universe_evaluation_staged
        from app.core.eval.evaluation_store import (
            generate_run_id,
            save_run,
            save_failed_run,
            update_latest_pointer,
            create_run_from_evaluation,
            acquire_run_lock,
            release_run_lock,
            write_run_running,
            get_current_run_status,
        )
    except ImportError as e:
        return {"started": False, "reason": f"Evaluation module not available: {e}", "run_id": None}

    if not UNIVERSE_SYMBOLS:
        return {"started": False, "reason": "Universe is empty - check config/universe.csv", "run_id": None}

    run_id = generate_run_id()
    started_at = datetime.now(timezone.utc).isoformat()
    market_phase = get_market_phase()

    if not acquire_run_lock(run_id, started_at):
        cur = get_current_run_status()
        current_run_id = cur.get("run_id") if cur else None
        logger.info("[EVAL] Evaluate now skipped: run already in progress run_id=%s", current_run_id)
        return {
            "started": False,
            "reason": "Evaluation already in progress",
            "run_id": current_run_id,
            "status": "RUNNING",
        }

    try:
        write_run_running(run_id, started_at)
    except Exception as e:
        logger.exception("[EVAL] write_run_running failed: %s", e)
        release_run_lock()
        raise HTTPException(status_code=500, detail=f"Failed to persist run state: {e}")

    try:
        logger.info("[EVAL] Staged evaluation started run_id=%s", run_id)
        result = run_universe_evaluation_staged(list(UNIVERSE_SYMBOLS), use_staged=True)
        run = create_run_from_evaluation(
            run_id=run_id,
            started_at=started_at,
            evaluation_result=result,
            market_phase=market_phase,
        )
        save_run(run)
        if run.status == "COMPLETED" and run.completed_at:
            update_latest_pointer(run_id, run.completed_at)
        logger.info("[EVAL] Run %s completed and persisted status=%s", run_id, run.status)
        try:
            from app.core.alerts.alert_engine import process_run_completed
            process_run_completed(run)
        except Exception as alert_err:
            logger.warning("[EVAL] Alert processing failed (non-fatal): %s", alert_err)
        release_run_lock()
        return {
            "started": True,
            "reason": "Evaluation completed",
            "run_id": run_id,
            "status": run.status,
            "engine": getattr(run, "engine", "staged"),
        }
    except Exception as e:
        logger.exception("Staged evaluation failed - aborting (no legacy fallback): %s", e)
        release_run_lock()
        save_failed_run(run_id, str(e), e, started_at)
        try:
            from app.core.alerts.alert_engine import process_run_completed
            from app.core.eval.evaluation_store import load_run
            failed_run = load_run(run_id)
            if failed_run:
                process_run_completed(failed_run)
        except Exception as alert_err:
            logger.warning("[EVAL] Alert processing for failed run (non-fatal): %s", alert_err)
        raise HTTPException(
            status_code=500,
            detail=f"Staged evaluation failed: {e}",
        )


@app.get("/api/view/universe-evaluation")
def api_view_universe_evaluation() -> Dict[str, Any]:
    """Get cached universe evaluation result with per-symbol rows."""
    from datetime import datetime, timezone
    try:
        from app.core.eval.universe_evaluator import get_cached_evaluation, get_evaluation_state
        
        state = get_evaluation_state()
        cached = get_cached_evaluation()
        
        if cached is None:
            return {
                "evaluation_state": state["evaluation_state"],
                "evaluation_state_reason": state["evaluation_state_reason"],
                "last_evaluated_at": None,
                "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
                "symbols": [],
                "alerts_count": 0,
            }
        
        # Convert dataclass results to dicts
        symbols_data = []
        for s in cached.symbols:
            candidate_trades = []
            position_open = getattr(s, "position_open", False)
            for ct in s.candidate_trades:
                # C4: Filter candidate trades by lifecycle (CSP vs CC)
                # If position is open -> show CC only
                # If position is not open -> show CSP only
                # Always include HOLD strategy
                strategy = ct.strategy
                if strategy == "HOLD":
                    pass  # Always include
                elif position_open and strategy == "CSP":
                    continue  # Skip CSP when position is open (show CC only)
                elif not position_open and strategy == "CC":
                    continue  # Skip CC when no position (show CSP only)
                
                # C6: Add CSP notional for sorting
                csp_notional = None
                if strategy == "CSP" and ct.strike is not None:
                    csp_notional = float(ct.strike) * 100
                
                candidate_trades.append({
                    "strategy": ct.strategy,
                    "expiry": ct.expiry,
                    "strike": ct.strike,
                    "delta": ct.delta,
                    "credit_estimate": ct.credit_estimate,
                    "max_loss": ct.max_loss,
                    "why_this_trade": ct.why_this_trade,
                    "csp_notional": csp_notional,  # Capital required for CSP
                })
            
            # Extract selected_contract if available (for Greeks summary linkage)
            selected_contract_info = None
            if hasattr(s, "stage2") and s.stage2 and hasattr(s.stage2, "selected_contract"):
                sc = s.stage2.selected_contract
                if sc:
                    selected_contract_info = {
                        "expiry": sc.expiration.isoformat() if hasattr(sc, "expiration") and sc.expiration else None,
                        "strike": sc.strike if hasattr(sc, "strike") else None,
                        "option_type": sc.option_type.value if hasattr(sc, "option_type") and sc.option_type else None,
                        "occ_symbol": sc.symbol if hasattr(sc, "symbol") else None,
                        "delta": sc.delta if hasattr(sc, "delta") else None,
                        "dte": sc.dte if hasattr(sc, "dte") else None,
                    }
            
            symbols_data.append({
                "symbol": s.symbol,
                "source": s.source,
                "price": s.price,
                "bid": s.bid,
                "ask": s.ask,
                "volume": s.volume,
                "avg_volume": s.avg_volume,
                "verdict": s.verdict,
                "primary_reason": _clean_encoding(s.primary_reason),
                "confidence": s.confidence,
                "score": s.score,
                "regime": s.regime,
                "risk": s.risk,
                "liquidity_ok": s.liquidity_ok,
                "liquidity_reason": _clean_encoding(s.liquidity_reason),
                "earnings_blocked": s.earnings_blocked,
                "earnings_days": s.earnings_days,
                "options_available": s.options_available,
                "options_reason": _clean_encoding(s.options_reason),
                "gates": s.gates,
                "blockers": s.blockers,
                "candidate_trades": candidate_trades,
                "fetched_at": s.fetched_at,
                "error": s.error,
                # Data quality fields
                "data_completeness": s.data_completeness,
                "missing_fields": s.missing_fields,
                "data_quality_details": s.data_quality_details,
                # Waiver info (B1: explicit for UI consumption)
                "waiver_reason": getattr(s, "waiver_reason", None),
                # Position awareness
                "position_open": getattr(s, "position_open", False),
                "position_reason": getattr(s, "position_reason", None),
                # Capital hint
                "capital_hint": s.capital_hint.to_dict() if hasattr(s, "capital_hint") and s.capital_hint else None,
                # Selected contract info (C3: for Greeks summary linkage)
                "selected_contract": selected_contract_info,
                # Phase 3: Explainable scoring and capital-aware ranking
                "score_breakdown": getattr(s, "score_breakdown", None),
                "rank_reasons": getattr(s, "rank_reasons", None),
                "csp_notional": getattr(s, "csp_notional", None),
                "notional_pct": getattr(s, "notional_pct", None),
                "band_reason": getattr(s, "band_reason", None),
            })
        
        # C6: Sort symbols by score desc, then CSP notional asc (to deprioritize high-notional CSPs)
        # This ensures COST ($900+ stock) doesn't float to top purely on score
        def sort_key(sym_data):
            score = sym_data.get("score") or 0
            # Get CSP notional from first CSP candidate trade if available
            csp_notional = float('inf')  # Default to high value (will sort last among equal scores)
            for ct in sym_data.get("candidate_trades", []):
                if ct.get("strategy") == "CSP" and ct.get("csp_notional"):
                    csp_notional = ct.get("csp_notional")
                    break
            # Sort: -score (descending), csp_notional (ascending)
            return (-score, csp_notional)
        
        symbols_data.sort(key=sort_key)
        
        return {
            "evaluation_state": cached.evaluation_state,
            "evaluation_state_reason": _clean_encoding(cached.evaluation_state_reason),
            "last_evaluated_at": cached.last_evaluated_at,
            "duration_seconds": cached.duration_seconds,
            "counts": {
                "total": cached.total,
                "evaluated": cached.evaluated,
                "eligible": cached.eligible,
                "shortlisted": cached.shortlisted,
            },
            "symbols": symbols_data,
            "alerts_count": len(cached.alerts),
            "errors": cached.errors,
        }
    except ImportError as e:
        return {
            "evaluation_state": "IDLE",
            "evaluation_state_reason": f"Evaluation module not available: {e}",
            "last_evaluated_at": None,
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "symbols": [],
            "alerts_count": 0,
        }
    except Exception as e:
        logger.exception("Error getting universe evaluation: %s", e)
        return {
            "evaluation_state": "FAILED",
            "evaluation_state_reason": f"Error: {e}",
            "last_evaluated_at": None,
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "symbols": [],
            "alerts_count": 0,
        }


@app.get("/api/view/evaluation-alerts")
def api_view_evaluation_alerts() -> Dict[str, Any]:
    """Get alerts generated from universe evaluation."""
    from datetime import datetime, timezone
    try:
        from app.core.eval.universe_evaluator import get_cached_evaluation
        
        cached = get_cached_evaluation()
        if cached is None:
            return {
                "alerts": [],
                "count": 0,
                "last_generated_at": None,
                "reason": "No evaluation run yet",
            }
        
        alerts_data = []
        for a in cached.alerts:
            alerts_data.append({
                "id": a.id,
                "type": a.type,
                "symbol": a.symbol,
                "message": _clean_encoding(a.message),
                "severity": a.severity,
                "created_at": a.created_at,
                "meta": a.meta,
            })
        
        return {
            "alerts": alerts_data,
            "count": len(alerts_data),
            "last_generated_at": cached.last_evaluated_at,
        }
    except ImportError:
        return {"alerts": [], "count": 0, "last_generated_at": None, "reason": "Evaluation module not available"}
    except Exception as e:
        logger.exception("Error getting evaluation alerts: %s", e)
        return {"alerts": [], "count": 0, "last_generated_at": None, "reason": f"Error: {e}"}


@app.get("/api/view/alert-log")
def api_view_alert_log() -> Dict[str, Any]:
    """Phase 6: Recent alert log (sent + suppressed) for Notifications page."""
    try:
        from app.core.alerts.alert_engine import list_recent_alert_records
        limit = 100
        records = list_recent_alert_records(limit=limit)
        return {"records": records, "count": len(records)}
    except ImportError:
        return {"records": [], "count": 0, "reason": "Alert module not available"}
    except Exception as e:
        logger.exception("Error getting alert log: %s", e)
        return {"records": [], "count": 0, "reason": str(e)}


@app.get("/api/view/lifecycle-log")
def api_view_lifecycle_log(limit: int = Query(default=100, ge=1, le=500)) -> Dict[str, Any]:
    """Phase 2C: Recent lifecycle log entries (position directives)."""
    try:
        from app.core.lifecycle.persistence import list_recent_lifecycle_entries
        records = list_recent_lifecycle_entries(limit=limit)
        return {"records": records, "count": len(records)}
    except ImportError:
        return {"records": [], "count": 0, "reason": "Lifecycle module not available"}
    except Exception as e:
        logger.exception("Error getting lifecycle log: %s", e)
        return {"records": [], "count": 0, "reason": str(e)}


@app.get("/api/ops/alerting-status")
def api_ops_alerting_status() -> Dict[str, Any]:
    """Phase 6: Whether Slack is configured (UI shows 'alerts suppressed' when not)."""
    try:
        from app.core.alerts.alert_engine import get_alerting_status
        return get_alerting_status()
    except ImportError:
        return {"slack_configured": False, "message": "Alert module not available"}
    except Exception as e:
        logger.exception("Error getting alerting status: %s", e)
        return {"slack_configured": False, "message": str(e)}


@app.get("/api/view/strategy-overview")
def api_view_strategy_overview() -> Dict[str, Any]:
    """
    Return the strategy overview markdown (docs/STRATEGY_OVERVIEW.md).
    Read-only; used by the Strategy page in the UI.
    """
    strategy_path = Path(__file__).resolve().parent.parent.parent / "docs" / "STRATEGY_OVERVIEW.md"
    try:
        content = strategy_path.read_text(encoding="utf-8")
        return {"content": content}
    except FileNotFoundError:
        logger.warning("Strategy overview file not found: %s", strategy_path)
        return {"content": "# Strategy Overview\n\nDocument not found."}
    except Exception as e:
        logger.exception("Error reading strategy overview: %s", e)
        return {"content": "# Strategy Overview\n\nError loading document."}


@app.get("/api/view/pipeline-doc")
def api_view_pipeline_doc() -> Dict[str, Any]:
    """
    Return the evaluation pipeline markdown (docs/EVALUATION_PIPELINE.md).
    Implementation-truthful reference; used by the Pipeline Details page.
    """
    pipeline_path = Path(__file__).resolve().parent.parent.parent / "docs" / "EVALUATION_PIPELINE.md"
    try:
        content = pipeline_path.read_text(encoding="utf-8")
        return {"content": content}
    except FileNotFoundError:
        logger.warning("Pipeline doc not found: %s", pipeline_path)
        return {"content": "# Evaluation Pipeline\n\nDocument not found."}
    except Exception as e:
        logger.exception("Error reading pipeline doc: %s", e)
        return {"content": "# Evaluation Pipeline\n\nError loading document."}


# ============================================================================
# TTS (OpenAI Text-to-Speech) — API key must be set in backend env only
# ============================================================================

TTS_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
TTS_MAX_CHARS = 4096


@app.post("/api/tts/speech")
async def api_tts_speech(request: Request) -> Response:
    """
    Proxy to OpenAI TTS. Body: { "text": string, "voice"?: "alloy"|"echo"|"fable"|"onyx"|"nova"|"shimmer" }.
    Returns audio/mpeg. Requires OPENAI_API_KEY in server environment.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing or empty text")
    voice = (body.get("voice") or "alloy").lower()
    if voice not in TTS_VOICES:
        voice = "alloy"
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS]
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("TTS requested but OPENAI_API_KEY is not set")
        raise HTTPException(
            status_code=503,
            detail="Text-to-speech is not configured. Set OPENAI_API_KEY on the server.",
        )
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "tts-1", "input": text, "voice": voice},
                timeout=30.0,
            )
    except Exception as e:
        logger.exception("OpenAI TTS request failed: %s", e)
        msg = str(e).strip() or "TTS request failed"
        if "connect" in msg.lower() or "refused" in msg.lower():
            msg = "Cannot reach OpenAI. Check network and that OPENAI_API_KEY is valid."
        raise HTTPException(status_code=502, detail=msg[:200])
    if resp.status_code != 200:
        logger.warning("OpenAI TTS error: %s %s", resp.status_code, (resp.text or "")[:200])
        detail = "TTS request failed"
        try:
            err_body = resp.json()
            err_info = err_body.get("error") or err_body
            msg = err_info.get("message") if isinstance(err_info, dict) else None
            code = err_info.get("code") if isinstance(err_info, dict) else None
            if msg:
                detail = f"OpenAI: {msg[:150]}" if not code else f"OpenAI ({resp.status_code}): {msg[:120]}"
        except Exception:
            if resp.status_code == 401:
                detail = "OpenAI: Invalid or expired API key. Check OPENAI_API_KEY in .env."
            elif resp.status_code == 429:
                detail = "OpenAI: Rate limit exceeded. Try again in a moment."
        raise HTTPException(status_code=502, detail=detail)
    return Response(content=resp.content, media_type="audio/mpeg")


# ============================================================================
# EVALUATION RUN PERSISTENCE ENDPOINTS
# ============================================================================

@app.get("/api/view/evaluation/latest")
def api_view_evaluation_latest() -> Dict[str, Any]:
    """
    Get the latest COMPLETED evaluation run.
    Returns counts, top candidates, and metadata.
    All screens should use this for consistent truth.
    """
    try:
        from app.core.eval.evaluation_store import build_latest_response
        return build_latest_response()
    except ImportError as e:
        return {
            "has_completed_run": False,
            "run_id": None,
            "status": "ERROR",
            "reason": f"Store module not available: {e}",
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
        }
    except Exception as e:
        logger.exception("Error getting latest evaluation: %s", e)
        return {
            "has_completed_run": False,
            "run_id": None,
            "status": "ERROR",
            "reason": f"Error: {e}",
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
        }


@app.get("/api/view/evaluation/runs")
def api_view_evaluation_runs(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
    """
    List recent evaluation runs (newest first).
    For the evaluation history page.
    """
    try:
        from app.core.eval.evaluation_store import build_runs_list_response
        return build_runs_list_response(limit)
    except ImportError as e:
        return {"runs": [], "count": 0, "latest_run_id": None, "reason": f"Store module not available: {e}"}
    except Exception as e:
        logger.exception("Error listing evaluation runs: %s", e)
        return {"runs": [], "count": 0, "latest_run_id": None, "reason": f"Error: {e}"}


@app.get("/api/view/evaluation/{run_id}")
def api_view_evaluation_run(run_id: str) -> Dict[str, Any]:
    """
    Get full details of a specific evaluation run.
    Includes all per-symbol results.
    """
    try:
        from app.core.eval.evaluation_store import build_run_detail_response
        return build_run_detail_response(run_id)
    except ImportError as e:
        return {"found": False, "run_id": run_id, "reason": f"Store module not available: {e}"}
    except Exception as e:
        logger.exception("Error getting evaluation run %s: %s", run_id, e)
        return {"found": False, "run_id": run_id, "reason": f"Error: {e}"}


@app.get("/api/view/evaluation/status/current")
def api_view_evaluation_status_current() -> Dict[str, Any]:
    """
    Get current evaluation status (Phase 5: persistent run lock).
    is_running and current_run_id from store lock file; last completed from latest pointer.
    """
    try:
        from app.core.eval.universe_evaluator import get_evaluation_state
        from app.core.eval.evaluation_store import load_latest_pointer, get_current_run_status

        cur = get_current_run_status()
        is_running = cur is not None
        current_run_id = cur.get("run_id") if cur else None
        started_at = cur.get("started_at") if cur else None
        pointer = load_latest_pointer()
        state = get_evaluation_state()
        return {
            "is_running": is_running,
            "current_run_id": current_run_id,
            "started_at": started_at,
            "evaluation_state": "RUNNING" if is_running else state.get("evaluation_state", "IDLE"),
            "evaluation_state_reason": state.get("evaluation_state_reason"),
            "last_completed_run_id": pointer.run_id if pointer else None,
            "last_completed_at": pointer.completed_at if pointer else None,
        }
    except ImportError as e:
        return {
            "is_running": False,
            "current_run_id": None,
            "evaluation_state": "ERROR",
            "evaluation_state_reason": f"Module not available: {e}",
            "last_completed_run_id": None,
            "last_completed_at": None,
        }
    except Exception as e:
        logger.exception("Error getting evaluation status: %s", e)
        return {
            "is_running": False,
            "current_run_id": None,
            "evaluation_state": "ERROR",
            "evaluation_state_reason": f"Error: {e}",
            "last_completed_run_id": None,
            "last_completed_at": None,
        }


# ============================================================================
# TRADE JOURNAL API
# ============================================================================

def _trade_dict_with_next_action(trade: "Any") -> Dict[str, Any]:
    """Return trade.to_dict() with next_action merged from next_actions.json if present."""
    from app.core.journal.store import get_next_actions
    d = trade.to_dict()
    next_actions = get_next_actions()
    if trade.trade_id in next_actions:
        d["next_action"] = next_actions[trade.trade_id]
    else:
        d["next_action"] = None
    return d


@app.get("/api/trades")
def api_trades_list(limit: int = Query(default=100, ge=1, le=500)) -> Dict[str, Any]:
    """List trades (newest first). Includes next_action from exit-rules when available."""
    try:
        from app.core.journal.store import list_trades
        trades = list_trades(limit=limit)
        return {"trades": [_trade_dict_with_next_action(t) for t in trades], "count": len(trades)}
    except ImportError as e:
        return {"trades": [], "count": 0, "error": str(e)}
    except Exception as e:
        logger.exception("Error listing trades: %s", e)
        return {"trades": [], "count": 0, "error": str(e)}


@app.get("/api/trades/export.csv")
def api_trades_export_csv(limit: int = Query(default=500, ge=1, le=2000)):
    """Export all trades as CSV."""
    from fastapi.responses import PlainTextResponse
    try:
        from app.core.journal.export import export_trades_csv
        csv_content = export_trades_csv(limit=limit)
        return PlainTextResponse(csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=trades_export.csv"})
    except Exception as e:
        logger.exception("Error exporting trades CSV: %s", e)
        return PlainTextResponse("trade_id,error\n," + str(e).replace("\n", " "), status_code=500)


@app.get("/api/trades/{trade_id}")
def api_trade_detail(trade_id: str) -> Dict[str, Any]:
    """Get a single trade by ID. Includes next_action from exit-rules when available."""
    try:
        from app.core.journal.store import get_trade
        trade = get_trade(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return _trade_dict_with_next_action(trade)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting trade %s: %s", trade_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades/{trade_id}/export.csv")
def api_trade_export_csv(trade_id: str):
    """Export a single trade as CSV."""
    from fastapi.responses import PlainTextResponse
    try:
        from app.core.journal.export import export_trade_csv
        csv_content = export_trade_csv(trade_id)
        if not csv_content:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return PlainTextResponse(csv_content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=trade_{trade_id}.csv"})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error exporting trade CSV: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trades")
async def api_trade_create(request: Request) -> Dict[str, Any]:
    """Create a new trade."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        from app.core.journal.store import create_trade
        trade = create_trade(body)
        return trade.to_dict()
    except Exception as e:
        logger.exception("Error creating trade: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/trades/{trade_id}")
async def api_trade_update(trade_id: str, request: Request) -> Dict[str, Any]:
    """Update an existing trade."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        from app.core.journal.store import update_trade
        trade = update_trade(trade_id, body)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return trade.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating trade %s: %s", trade_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/trades/{trade_id}")
def api_trade_delete(trade_id: str) -> Dict[str, Any]:
    """Delete a trade."""
    try:
        from app.core.journal.store import delete_trade
        ok = delete_trade(trade_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return {"deleted": True, "trade_id": trade_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting trade %s: %s", trade_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trades/{trade_id}/fills")
async def api_trade_add_fill(trade_id: str, request: Request) -> Dict[str, Any]:
    """Add a fill (OPEN or CLOSE) to a trade."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        from app.core.journal.store import add_fill
        trade = add_fill(trade_id, body)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return trade.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding fill to trade %s: %s", trade_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trades/alerts")
def api_trades_alerts(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    """List recent journal alerts (stop breached, target hit)."""
    try:
        from app.core.journal.store import _get_journal_dir
        import json
        out_dir = _get_journal_dir()
        alerts_path = out_dir / "alerts.jsonl"
        alerts = []
        if alerts_path.exists():
            with open(alerts_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines[-limit:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    alerts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return {"alerts": list(reversed(alerts)), "count": len(alerts)}
    except ImportError:
        return {"alerts": [], "count": 0}
    except Exception as e:
        logger.exception("Error listing journal alerts: %s", e)
        return {"alerts": [], "count": 0, "error": str(e)}


@app.delete("/api/trades/{trade_id}/fills/{fill_id}")
def api_trade_delete_fill(trade_id: str, fill_id: str) -> Dict[str, Any]:
    """Remove a fill from a trade."""
    try:
        from app.core.journal.store import delete_fill
        trade = delete_fill(trade_id, fill_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} or fill {fill_id} not found")
        return trade.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting fill %s from trade %s: %s", fill_id, trade_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 1: ACCOUNTS — CAPITAL AWARENESS
# ============================================================================


@app.get("/api/accounts")
def api_accounts_list() -> Dict[str, Any]:
    """List all accounts."""
    try:
        from app.core.accounts.service import list_accounts
        accounts = list_accounts()
        return {"accounts": [a.to_dict() for a in accounts], "count": len(accounts)}
    except Exception as e:
        logger.exception("Error listing accounts: %s", e)
        return {"accounts": [], "count": 0, "error": str(e)}


@app.get("/api/accounts/default")
def api_accounts_default() -> Dict[str, Any]:
    """Get the default account."""
    try:
        from app.core.accounts.service import get_default_account
        account = get_default_account()
        if account is None:
            return {"account": None, "message": "No default account set"}
        return {"account": account.to_dict()}
    except Exception as e:
        logger.exception("Error getting default account: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/accounts")
async def api_accounts_create(request: Request) -> Dict[str, Any]:
    """Create a new account."""
    try:
        import asyncio
        body = await request.json()
        from app.core.accounts.service import create_account
        account, errors = create_account(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return account.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating account: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/accounts/{account_id}")
async def api_accounts_update(account_id: str, request: Request) -> Dict[str, Any]:
    """Update an existing account."""
    try:
        body = await request.json()
        from app.core.accounts.service import update_account
        account, errors = update_account(account_id, body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return account.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating account %s: %s", account_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/accounts/{account_id}/set-default")
def api_accounts_set_default(account_id: str) -> Dict[str, Any]:
    """Set an account as the default."""
    try:
        from app.core.accounts.service import set_default
        account, errors = set_default(account_id)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return account.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error setting default account %s: %s", account_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/accounts/{account_id}/csp-sizing")
def api_accounts_csp_sizing(account_id: str, strike: float = Query(..., gt=0)) -> Dict[str, Any]:
    """Compute CSP position sizing for a given strike price and account."""
    try:
        from app.core.accounts.service import get_account, compute_csp_sizing
        account = get_account(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        sizing = compute_csp_sizing(account, strike)
        return sizing
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error computing CSP sizing: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 3: PORTFOLIO & RISK INTELLIGENCE
# ============================================================================


@app.get("/api/portfolio/summary")
def api_portfolio_summary() -> Dict[str, Any]:
    """Phase 3: Portfolio summary — total_equity, capital_in_use, available_capital, risk_flags."""
    try:
        from app.core.accounts.store import list_accounts
        from app.core.positions.store import list_positions
        from app.core.portfolio.service import compute_portfolio_summary

        accounts = list_accounts()
        positions = list_positions()
        summary = compute_portfolio_summary(accounts, positions)
        return {
            "total_equity": round(summary.total_equity, 2),
            "capital_in_use": round(summary.capital_in_use, 2),
            "available_capital": round(summary.available_capital, 2),
            "capital_utilization_pct": round(summary.capital_utilization_pct, 4),
            "open_positions_count": summary.open_positions_count,
            "available_capital_clamped": summary.available_capital_clamped,
            "risk_flags": [
                {"code": f.code, "message": f.message, "severity": f.severity}
                for f in summary.risk_flags
            ],
        }
    except Exception as e:
        logger.exception("Error fetching portfolio summary: %s", e)
        return {
            "total_equity": 0,
            "capital_in_use": 0,
            "available_capital": 0,
            "capital_utilization_pct": 0,
            "open_positions_count": 0,
            "available_capital_clamped": False,
            "risk_flags": [],
            "error": str(e),
        }


@app.get("/api/portfolio/exposure")
def api_portfolio_exposure(
    group_by: str = Query(default="symbol", description="Group by: symbol | sector"),
) -> Dict[str, Any]:
    """Phase 3: Exposure by symbol or sector."""
    try:
        from app.core.accounts.store import list_accounts
        from app.core.positions.store import list_positions
        from app.core.portfolio.service import compute_exposure

        accounts = list_accounts()
        positions = list_positions()
        group = "sector" if group_by == "sector" else "symbol"
        items = compute_exposure(accounts, positions, group_by=group)
        return {"items": items, "group_by": group}
    except Exception as e:
        logger.exception("Error fetching portfolio exposure: %s", e)
        return {"items": [], "group_by": group_by if group_by else "symbol", "error": str(e)}


@app.get("/api/portfolio/risk-profile")
def api_portfolio_risk_profile() -> Dict[str, Any]:
    """Phase 3: Risk profile settings."""
    try:
        from app.core.portfolio.store import load_risk_profile
        p = load_risk_profile()
        return p.to_dict()
    except Exception as e:
        logger.exception("Error fetching risk profile: %s", e)
        return {"error": str(e)}


@app.put("/api/portfolio/risk-profile")
async def api_portfolio_risk_profile_put(request: Request) -> Dict[str, Any]:
    """Phase 3: Update risk profile settings."""
    try:
        body = await request.json()
        from app.core.portfolio.store import update_risk_profile
        p = update_risk_profile(body)
        return p.to_dict()
    except Exception as e:
        logger.exception("Error updating risk profile: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# PHASE 2A: DASHBOARD OPPORTUNITIES — RANKED DECISION INTELLIGENCE
# ============================================================================


# Phase 8A: Backend constraint for opportunities limit (UI must not receive 422)
DASHBOARD_OPPORTUNITIES_LIMIT_MIN = 1
DASHBOARD_OPPORTUNITIES_LIMIT_MAX = 50
DASHBOARD_OPPORTUNITIES_LIMIT_DEFAULT = 5


def _clamp_opportunities_limit(value: Any) -> int:
    """Clamp limit to valid range so normal UI usage never gets 422."""
    try:
        n = int(value) if value is not None else DASHBOARD_OPPORTUNITIES_LIMIT_DEFAULT
    except (TypeError, ValueError):
        n = DASHBOARD_OPPORTUNITIES_LIMIT_DEFAULT
    return max(DASHBOARD_OPPORTUNITIES_LIMIT_MIN, min(DASHBOARD_OPPORTUNITIES_LIMIT_MAX, n))


@app.get("/api/dashboard/opportunities")
def api_dashboard_opportunities(
    limit: Optional[Any] = Query(default=None, description="Max results (1–50); clamped server-side to avoid 422"),
    strategy: Optional[str] = Query(default=None),
    max_capital_pct: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    include_blocked: bool = Query(default=False, description="Phase 3: Include BLOCKED opportunities with risk_reasons"),
) -> Dict[str, Any]:
    """Ranked opportunities for the dashboard.

    Returns top opportunities sorted by band, score, and capital efficiency.
    Each symbol appears at most once with its primary strategy (exclusivity rule).
    Phase 3: Each opportunity includes risk_status (OK/WARN/BLOCKED) and risk_reasons.

    Query params:
      - limit: Max results (default 5, max 50); values outside 1–50 are clamped (no 422).
      - strategy: Filter by strategy (CSP, CC, STOCK)
      - max_capital_pct: Filter by max capital % (0.0-1.0)
      - include_blocked: Include BLOCKED opportunities with block reasons
    """
    limit = _clamp_opportunities_limit(limit)
    try:
        from app.core.ranking.service import get_dashboard_opportunities
        return get_dashboard_opportunities(
            limit=limit,
            strategy_filter=strategy,
            max_capital_pct=max_capital_pct,
            include_blocked=include_blocked,
        )
    except Exception as e:
        logger.exception("Error fetching dashboard opportunities: %s", e)
        return {
            "opportunities": [],
            "count": 0,
            "evaluation_id": None,
            "evaluated_at": None,
            "account_equity": None,
            "total_eligible": 0,
            "error": str(e),
        }


# ============================================================================
# PHASE 2B: SYMBOL INTELLIGENCE — EXPLAIN, CANDIDATES, TARGETS
# ============================================================================


@app.get("/api/symbols/{symbol}/explain")
def api_symbols_explain(symbol: str) -> Dict[str, Any]:
    """Ticker explain: gate trace, band, score, strategy decision, capital sizing."""
    try:
        from app.core.symbols.explain import get_symbol_explain
        return get_symbol_explain(symbol)
    except Exception as e:
        logger.exception("Error fetching symbol explain: %s", e)
        return {"symbol": symbol, "error": str(e)}


@app.get("/api/symbols/{symbol}/candidates")
def api_symbols_candidates(
    symbol: str,
    strategy: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Top 3 contract candidates for CSP or CC with sizing."""
    try:
        from app.core.symbols.candidates import get_symbol_candidates
        return get_symbol_candidates(symbol, strategy=strategy)
    except Exception as e:
        logger.exception("Error fetching symbol candidates: %s", e)
        return {"symbol": symbol, "candidates": [], "error": str(e)}


@app.get("/api/symbols/{symbol}/targets")
def api_symbols_targets_get(symbol: str) -> Dict[str, Any]:
    """Get stored stock entry/exit targets for symbol."""
    try:
        from app.core.symbols.targets import get_targets
        return get_targets(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error fetching symbol targets: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/symbols/{symbol}/targets")
async def api_symbols_targets_put(symbol: str, request: Request) -> Dict[str, Any]:
    """Store stock entry/exit targets for symbol."""
    try:
        body = await request.json()
        from app.core.symbols.targets import put_targets
        return put_targets(symbol, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error storing symbol targets: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/symbols/{symbol}/company")
def api_symbols_company(symbol: str) -> Dict[str, Any]:
    """Company metadata for symbol (local dict, no external API)."""
    try:
        from app.core.market.company_data import get_company_metadata
        meta = get_company_metadata(symbol)
        if meta is None:
            return {"symbol": symbol.strip().upper(), "name": None, "sector": None, "industry": None}
        return meta
    except Exception as e:
        logger.exception("Error fetching company metadata: %s", e)
        return {"symbol": symbol, "error": str(e)}


# ============================================================================
# PHASE 1: POSITIONS — MANUAL EXECUTION TRACKING
# ============================================================================


def _lifecycle_for_position(position_id: str, lifecycle_records: list) -> Dict[str, Any]:
    """Phase 2C: Last lifecycle entry for a position."""
    for r in lifecycle_records:
        if r.get("position_id") == position_id:
            return {
                "lifecycle_state": r.get("lifecycle_state"),
                "last_directive": r.get("directive") or r.get("reason") or r.get("action", ""),
                "last_alert_at": r.get("triggered_at"),
            }
    return {"lifecycle_state": None, "last_directive": None, "last_alert_at": None}


@app.get("/api/positions/tracked")
def api_positions_tracked(
    status: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """List manually tracked positions, optionally filtered by symbol. Phase 2C: includes lifecycle_state, last_directive, last_alert_at."""
    try:
        from app.core.positions.service import list_positions
        from app.core.lifecycle.persistence import list_recent_lifecycle_entries
        positions = list_positions(status=status, symbol=symbol)
        lifecycle_records = list_recent_lifecycle_entries(limit=200)
        out = []
        for p in positions:
            d = p.to_dict()
            lc = _lifecycle_for_position(p.position_id, lifecycle_records)
            d["lifecycle_state"] = lc.get("lifecycle_state")
            d["last_directive"] = lc.get("last_directive")
            d["last_alert_at"] = lc.get("last_alert_at")
            out.append(d)
        return {"positions": out, "count": len(out)}
    except Exception as e:
        logger.exception("Error listing tracked positions: %s", e)
        return {"positions": [], "count": 0, "error": str(e)}


@app.post("/api/positions/manual-execute")
async def api_positions_manual_execute(request: Request) -> Dict[str, Any]:
    """Record a manual execution (creates a tracked position).

    IMPORTANT: This does NOT place a trade. It records the user's intention
    to execute and creates a Position record. The user must execute the
    actual trade in their brokerage account.
    """
    try:
        body = await request.json()
        from app.core.positions.service import manual_execute
        position, errors = manual_execute(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error recording manual execution: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/positions/tracked/{position_id}")
def api_positions_tracked_detail(position_id: str) -> Dict[str, Any]:
    """Get a single tracked position with lifecycle and exit info. Phase 4."""
    try:
        from app.core.positions.service import get_position
        from app.core.lifecycle.persistence import list_recent_lifecycle_entries
        from app.core.exits.store import load_exit, load_exit_events
        from app.core.symbols.data_sufficiency import get_data_sufficiency_for_position
        pos = get_position(position_id)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
        d = pos.to_dict()
        lc = _lifecycle_for_position(position_id, list_recent_lifecycle_entries(limit=200))
        d["lifecycle_state"] = lc.get("lifecycle_state")
        d["last_directive"] = lc.get("last_directive")
        d["last_alert_at"] = lc.get("last_alert_at")
        exit_events = load_exit_events(position_id)
        exit_rec = load_exit(position_id)
        d["exit"] = exit_rec.to_dict() if exit_rec else None
        d["exit_events"] = [e.to_dict() for e in exit_events]
        ds = get_data_sufficiency_for_position(
            pos.symbol,
            override=getattr(pos, "data_sufficiency_override", None),
            override_source=getattr(pos, "data_sufficiency_override_source", None),
        )
        d["data_sufficiency"] = ds["status"]
        d["data_sufficiency_missing_fields"] = ds.get("missing_fields") or []
        d["data_sufficiency_is_override"] = ds.get("is_override", False)
        d["required_data_missing"] = ds.get("required_data_missing") or []
        d["optional_data_missing"] = ds.get("optional_data_missing") or []
        d["required_data_stale"] = ds.get("required_data_stale") or []
        d["data_as_of_orats"] = ds.get("data_as_of_orats")
        d["data_as_of_price"] = ds.get("data_as_of_price")
        if exit_rec:
            from app.core.decision_quality.derived import compute_derived_metrics
            from app.core.portfolio.service import _capital_for_position
            events_pnl = sum(float(getattr(e, "realized_pnl", 0)) for e in exit_events)
            derived = compute_derived_metrics(
                pos, exit_rec, aggregated_realized_pnl=events_pnl,
                capital=_capital_for_position(pos),
                risk_amount=getattr(pos, "risk_amount_at_entry", None),
            )
            d["return_on_risk"] = derived.get("return_on_risk")
            d["return_on_risk_status"] = derived.get("return_on_risk_status") or "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"
            d["outcome_tag"] = derived.get("outcome_tag")
            d["time_in_trade_days"] = derived.get("time_in_trade_days")
        else:
            d["return_on_risk"] = None
            d["return_on_risk_status"] = "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"
            d["outcome_tag"] = None
            d["time_in_trade_days"] = None
        return d
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting position %s: %s", position_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/positions/{position_id}/exit")
async def api_positions_log_exit(position_id: str, request: Request) -> Dict[str, Any]:
    """Log a manual exit for a position. Phase 4: updates position to CLOSED."""
    try:
        body = await request.json()
        from app.core.exits.service import log_exit
        record, errors = log_exit(position_id, body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return {"exit": record.to_dict(), "position_id": position_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error logging exit for %s: %s", position_id, e)
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# DECISION QUALITY (Phase 4)
# ============================================================================

@app.get("/api/decision-quality/summary")
def api_decision_quality_summary() -> Dict[str, Any]:
    """Phase 4: Outcome summary — Win/Scratch/Loss, avg time in trade, capital days."""
    try:
        from app.core.decision_quality.analytics import get_outcome_summary
        return get_outcome_summary()
    except Exception as e:
        logger.exception("Error getting decision quality summary: %s", e)
        return {"status": "ERROR", "error": str(e)}


@app.get("/api/decision-quality/strategy-health")
def api_decision_quality_strategy_health() -> Dict[str, Any]:
    """Phase 4: Strategy health — CSP/CC/STOCK Win %, Loss %, avg duration, Abort %."""
    try:
        from app.core.decision_quality.analytics import get_strategy_health
        return get_strategy_health()
    except Exception as e:
        logger.exception("Error getting strategy health: %s", e)
        return {"status": "ERROR", "error": str(e)}


@app.get("/api/decision-quality/exit-discipline")
def api_decision_quality_exit_discipline() -> Dict[str, Any]:
    """Phase 4: Exit discipline — % aligned with lifecycle, manual overrides."""
    try:
        from app.core.decision_quality.analytics import get_exit_discipline
        return get_exit_discipline()
    except Exception as e:
        logger.exception("Error getting exit discipline: %s", e)
        return {"status": "ERROR", "error": str(e)}


@app.get("/api/decision-quality/band-outcome")
def api_decision_quality_band_outcome() -> Dict[str, Any]:
    """Phase 4: Band × Outcome matrix."""
    try:
        from app.core.decision_quality.analytics import get_band_outcome_matrix
        return get_band_outcome_matrix()
    except Exception as e:
        logger.exception("Error getting band outcome matrix: %s", e)
        return {"status": "ERROR", "error": str(e)}


@app.get("/api/symbols/{symbol}/data-sufficiency")
def api_symbol_data_sufficiency(symbol: str) -> Dict[str, Any]:
    """Phase 6: Data sufficiency from dependency rules. Returns status, missing_fields, required/optional/stale, data_as_of."""
    try:
        from app.core.symbols.data_sufficiency import derive_data_sufficiency_with_dependencies
        out = derive_data_sufficiency_with_dependencies(symbol)
        return {
            "symbol": symbol.strip().upper(),
            "status": out["status"],
            "missing_fields": out["missing_fields"],
            "required_data_missing": out.get("required_data_missing") or [],
            "optional_data_missing": out.get("optional_data_missing") or [],
            "required_data_stale": out.get("required_data_stale") or [],
            "data_as_of_orats": out.get("data_as_of_orats"),
            "data_as_of_price": out.get("data_as_of_price"),
        }
    except Exception as e:
        logger.exception("Error deriving data sufficiency for %s: %s", symbol, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/decision-quality/abort-effectiveness")
def api_decision_quality_abort_effectiveness() -> Dict[str, Any]:
    """Phase 4: Abort effectiveness."""
    try:
        from app.core.decision_quality.analytics import get_abort_effectiveness
        return get_abort_effectiveness()
    except Exception as e:
        logger.exception("Error getting abort effectiveness: %s", e)
        return {"status": "ERROR", "error": str(e)}


# ============================================================================
# SLACK NOTIFICATION ENDPOINT
# ============================================================================

def _persist_slack_delivery(sent: bool, status_code: Optional[int], reason: str, response_body: Optional[str] = None) -> None:
    """Persist Slack delivery status for diagnostics (Phase E)."""
    import json as _json
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    log_dir = base / "notifications"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "slack_delivery.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sent": sent,
        "status_code": status_code,
        "reason": reason[:500] if reason else None,
        "response_body": (response_body[:500] if response_body else None),
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_json.dumps(record, default=str) + "\n")
    except Exception as e:
        logger.warning("[SLACK] Failed to persist delivery status: %s", e)


@app.post("/api/ops/notify/slack")
def api_ops_notify_slack(request: Request):
    """
    Post message to Slack webhook.
    Returns HTTP 200 with body: sent=True when Slack confirms delivery; sent=False when
    not configured (reason + setup_hint) or when Slack API fails (reason + status_code).
    Use configured=False in response to show setup hint in UI instead of error.
    If no text/meta provided, builds a default message from the latest evaluation run.
    """
    import asyncio
    import requests as req
    
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        _persist_slack_delivery(False, None, "Slack not configured")
        # Return 200 so clients can show setup hint instead of error; sent=False indicates no delivery
        return JSONResponse(
            status_code=200,
            content={
                "sent": False,
                "configured": False,
                "reason": "Slack not configured - set SLACK_WEBHOOK_URL environment variable",
                "setup_hint": "Add SLACK_WEBHOOK_URL to your .env (see docs) and restart the backend.",
                "slack_response_body": None,
            },
        )
    
    try:
        body = asyncio.get_event_loop().run_until_complete(request.json())
    except Exception:
        body = {}
    
    channel = body.get("channel")
    text = body.get("text", "")
    meta = body.get("meta", {})
    
    # Build message from meta if provided
    if meta and not text:
        symbol = meta.get("symbol", "?")
        strategy = meta.get("strategy", "?")
        expiry = meta.get("expiry", "?")
        strike = meta.get("strike", "?")
        delta = meta.get("delta", "?")
        credit = meta.get("credit_estimate", "?")
        score = meta.get("score", "?")
        reason = meta.get("reason", "")[:50]
        run_id = meta.get("run_id", "?")
        verdict = meta.get("verdict", strategy)
        
        # Format credit nicely
        if credit != "?" and credit is not None:
            try:
                credit = f"${float(credit):.2f}"
            except (TypeError, ValueError):
                pass
        
        text = f":chart_with_upwards_trend: *ChakraOps Alert*\n"
        text += f"*{symbol}* | {verdict} | Score: {score}\n"
        if expiry != "?" and strike != "?":
            text += f"Strategy: {strategy} | Exp: {expiry} | Strike: {strike}"
            if delta != "?":
                text += f" | Delta: {delta}"
            if credit != "?":
                text += f" | Credit: {credit}"
            text += "\n"
        if reason:
            text += f"Reason: {reason}\n"
        if run_id != "?":
            text += f"_Run: {run_id[-12:] if len(str(run_id)) > 12 else run_id}_"
    
    # If still no text, try to build from latest evaluation run
    if not text:
        try:
            from app.core.eval.evaluation_store import build_latest_response
            latest = build_latest_response()
            if latest.get("has_completed_run"):
                run_id = latest.get("run_id", "unknown")
                counts = latest.get("counts", {})
                eligible = counts.get("eligible", 0)
                evaluated = counts.get("evaluated", 0)
                top = latest.get("top_candidates", [])
                
                text = f":chart_with_upwards_trend: *ChakraOps Evaluation Complete*\n"
                text += f"Evaluated: {evaluated} | Eligible: {eligible}\n"
                if top:
                    symbols_str = ", ".join([t.get("symbol", "?") for t in top[:5]])
                    text += f"Top candidates: {symbols_str}\n"
                else:
                    text += "No eligible candidates today.\n"
                text += f"_Run: {run_id[-12:] if len(str(run_id)) > 12 else run_id}_"
            else:
                text = ":warning: ChakraOps: No completed evaluation run available."
        except Exception as e:
            text = f":warning: ChakraOps notification (context unavailable: {e})"
    
    payload = {"text": text}
    if channel:
        payload["channel"] = channel
    
    try:
        resp = req.post(webhook_url, json=payload, timeout=10)
        response_body = resp.text[:500] if resp.text else None
        if resp.status_code == 200:
            _persist_slack_delivery(True, 200, "ok")
            return {"sent": True, "reason": None}
        _persist_slack_delivery(False, resp.status_code, f"Slack returned {resp.status_code}", response_body)
        logger.warning("[SLACK] Delivery failed status=%s body=%s", resp.status_code, response_body)
        return JSONResponse(
            status_code=503,
            content={
                "sent": False, 
                "reason": f"Slack returned {resp.status_code}", 
                "status_code": resp.status_code,
                "slack_response_body": response_body
            },
        )
    except Exception as e:
        _persist_slack_delivery(False, None, str(e))
        logger.exception("[SLACK] Request failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"sent": False, "reason": f"Slack request failed: {e}", "slack_response_body": None},
        )


# ============================================================================
# ENCODING HELPER
# ============================================================================

def _clean_encoding(s: Any) -> str:
    """Clean string encoding: replace em-dash and other non-ASCII with ASCII equivalents."""
    if s is None:
        return ""
    text = str(s)
    # Replace common problematic characters
    text = text.replace(" - ", " - ")  # em-dash
    text = text.replace("–", "-")    # en-dash
    text = text.replace("'", "'")    # smart quote
    text = text.replace("'", "'")    # smart quote
    text = text.replace(""", '"')    # smart quote
    text = text.replace(""", '"')    # smart quote
    text = text.replace("…", "...")  # ellipsis
    return text


