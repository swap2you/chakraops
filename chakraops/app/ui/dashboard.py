#!/usr/bin/env python3
"""ChakraOps Dashboard - Streamlit web interface (Legacy Position Management).

⚠️ NOTE: This is the legacy position management dashboard (trades, positions, alerts).
For Phase 7 decision intelligence dashboard, use:
- scripts/live_dashboard.py (launches app/ui/live_decision_dashboard.py)

This dashboard remains for position management workflows but is separate from Phase 7.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from app.core.engine.csp_trade_engine import CSPTradeEngine
from app.core.engine.position_engine import PositionEngine
from app.core.engine.risk_engine import RiskEngine
from app.core.engine.roll_engine import RollEngine
from app.core.engine.actions import (
    ActionType,
    Urgency,
    decide_position_action,
)
from app.core.action_engine import evaluate_position_action
from app.core.portfolio.portfolio_engine import PortfolioEngine
from app.core.state_machine.position_state_machine import (
    PositionState,
    get_allowed_transitions,
)
from app.core.persistence import (
    record_trade,
    upsert_position_from_trade,
    list_open_positions as persistence_list_open_positions,
    mark_candidate_executed,
    list_candidates as persistence_list_candidates,
    list_alerts,
    ack_alert,
    archive_alert,
    bulk_ack_alerts,
    bulk_archive_non_action_alerts,
    save_portfolio_snapshot,
    get_latest_portfolio_snapshot,
    get_enabled_symbols,
    get_all_symbols,
    add_symbol,
    update_symbol,
    toggle_symbol,
    delete_symbol,
    list_universe_symbols,
    add_universe_symbol,
    toggle_universe_symbol,
    delete_universe_symbol,
    get_assignment_profile,
    set_assignment_override,
    is_assignment_blocked,
)
from app.core.symbol_cache import (
    fetch_and_cache_theta_symbols,
    search_symbols,
    get_cached_symbol_count,
)
from app.core.market_time import get_market_state, is_market_open
from app.core.heartbeat import HeartbeatManager, REGIME_STALE_THRESHOLD_MINUTES
from app.core.dev_utils import reset_local_trading_state

# Set page config
st.set_page_config(
    page_title="ChakraOps Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "regime_cache" not in st.session_state:
    st.session_state.regime_cache = None
if "candidates_cache" not in st.session_state:
    st.session_state.candidates_cache = None
if "record_execution_modal" not in st.session_state:
    st.session_state.record_execution_modal = None
if "show_reset_confirm" not in st.session_state:
    st.session_state.show_reset_confirm = False
if "selected_brokerage" not in st.session_state:
    st.session_state.selected_brokerage = "Robinhood"
if "heartbeat_started" not in st.session_state:
    st.session_state.heartbeat_started = False
if "show_add_symbol_modal" not in st.session_state:
    st.session_state.show_add_symbol_modal = False

# Defensive check: ensure all required tables exist on startup (Phase 1B fix)
try:
    from app.core.persistence import init_persistence_db
    init_persistence_db()
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to initialize persistence database on dashboard startup: {e}")
    # Don't fail dashboard load, but log the error


def get_db_path() -> Path:
    """Get path to SQLite database.
    
    Returns the canonical DB_PATH from app.core.config.paths.
    This ensures all modules use the same database file.
    """
    from app.core.config.paths import DB_PATH
    return DB_PATH


def db_exists() -> bool:
    """Check if database exists."""
    return get_db_path().exists()


@st.cache_data(ttl=60)
def get_data_mode_status() -> Dict[str, Any]:
    """
    Fetch Data Mode / Realtime health for the dashboard indicator.
    Calls ORATS capabilities probe in-process; never blocks decision logic.
    Returns a small dict for UI display. Cached 60s. On any failure, returns FAIL and notes (no crash).
    """
    out = {
        "active_mode": "SNAPSHOT",
        "realtime_health": "FAIL",
        "source": "ORATS",
        "notes": [],
    }
    try:
        from app.core.options.orats_diagnostics import run_orats_diagnostic

        diag = run_orats_diagnostic("SPY")
        # Overall ORATS health = PASS if option_available == True
        option_available = bool(diag.get("option_available"))
        stock_available = bool(diag.get("stock_available"))
        index_available = diag.get("index_available")  # May be None if not tested
        
        exp_ok = bool(diag.get("theta_expirations_ok"))
        chain_ok = bool(diag.get("theta_chain_ok"))
        err = diag.get("error")

        if option_available:
            out["realtime_health"] = "PASS"
        elif exp_ok or chain_ok:
            out["realtime_health"] = "WARN"
        else:
            out["realtime_health"] = "FAIL"

        notes: list[str] = []
        notes.append(
            f"now_et={diag.get('now_et')} market_state={diag.get('market_state')} is_market_open={diag.get('is_market_open')}"
        )
        # Availability flags
        notes.append(
            f"stock_available={stock_available} option_available={option_available} index_available={index_available}"
        )
        if diag.get("stock_error"):
            notes.append(f"stock_error={diag.get('stock_error_type')}: {diag.get('stock_error')}")
        if diag.get("index_error"):
            notes.append(f"index_error={diag.get('index_error_type')}: {diag.get('index_error')}")
        # Option details
        notes.append(
            f"exp_ok={exp_ok} count={diag.get('expirations_count')} first_exp={diag.get('first_expiration')} "
            f"lat_ms_exp={diag.get('latency_ms_expirations')}"
        )
        notes.append(
            f"chain_ok={chain_ok} count={diag.get('contracts_count')} lat_ms_chain={diag.get('latency_ms_chain')}"
        )
        sample = diag.get("sample_contract") or {}
        if sample:
            notes.append(
                "sample_contract="
                + ", ".join(
                    f"{k}={sample.get(k)}"
                    for k in ("strike", "expiry", "bid", "ask", "delta", "iv", "open_interest")
                )
            )
        if err:
            notes.append(f"error_type={diag.get('error_type')} error={err}")
        out["notes"] = notes
    except Exception as e:
        out["notes"] = [f"theta_diagnostic_failed: {e}"]
    return out


def get_shadow_realtime_regime() -> Optional[Dict[str, Any]]:
    """
    Compute shadow realtime regime (read-only, not used for decisions).
    Reuses cached realtime health from get_data_mode_status(). If realtime
    health is FAIL, returns None. If PASS/WARN, fetches ORATS-derived signals
    via tools.theta_shadow_signals and calls the Phase 3 market_regime_engine.
    If all theta signals are unavailable, returns None. On any error, returns
    None; never raises.
    """
    try:
        import sys
        data_mode = get_data_mode_status()
        if data_mode.get("realtime_health") == "FAIL":
            return None

        _root = Path(__file__).resolve().parent.parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))

        from tools.theta_shadow_signals import get_theta_shadow_signals
        from tools.market_regime_engine import compute_market_regime

        theta_signals = get_theta_shadow_signals("SPY")
        price_trend = theta_signals.get("price_trend", "unavailable")
        volatility = theta_signals.get("volatility", "unavailable")
        liquidity = theta_signals.get("liquidity", "unavailable")
        theta_notes = list(theta_signals.get("notes") or [])

        if price_trend == "unavailable" and volatility == "unavailable" and liquidity == "unavailable":
            return None

        health = data_mode.get("realtime_health", "WARN")
        inputs = {
            "source": "REALTIME",
            "health": health,
            "price_trend": price_trend,
            "volatility": volatility,
            "liquidity": liquidity,
            "notes": ["shadow evaluation"] + theta_notes,
        }

        result = compute_market_regime(inputs)
        result["realtime_health"] = health
        return result
    except Exception:
        return None


def get_regime_snapshot() -> Optional[Dict[str, Any]]:
    """Read latest regime snapshot from database."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Try to read from regime_snapshots table
        cursor.execute("""
            SELECT regime, confidence, details, created_at
            FROM regime_snapshots
            ORDER BY created_at DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            import json
            return {
                "regime": row[0],
                "confidence": row[1],
                "details": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
            }
    except sqlite3.OperationalError:
        # Table doesn't exist
        return None
    except Exception:
        return None

    return None


def get_csp_candidates() -> List[Dict[str, Any]]:
    """Legacy function - DEPRECATED.
    
    Returns empty list. CSP candidates are now stored in csp_evaluations table.
    Use get_csp_evaluations(snapshot_id) instead.
    """
    return []


def get_alerts(limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get latest alerts from database."""
    try:
        alerts = list_alerts(status=status)
        return alerts[:limit]
    except Exception:
        return []


def get_last_update_time() -> Optional[str]:
    """Get the most recent update time from any table."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get latest from regime_snapshots
        cursor.execute("""
            SELECT MAX(created_at) FROM regime_snapshots
        """)
        regime_time = cursor.fetchone()[0]

        # Get latest from csp_evaluations
        cursor.execute("""
            SELECT MAX(created_at) FROM csp_evaluations
        """)
        candidates_time = cursor.fetchone()[0]

        conn.close()

        # Return the most recent
        times = [t for t in [regime_time, candidates_time] if t]
        if times:
            return max(times)
        return None
    except Exception:
        return None


def get_level_color(level: str) -> str:
    """Get color for alert level."""
    level_upper = level.upper()
    if level_upper == "HALT":
        return "🔴"
    elif level_upper == "ACTION":
        return "🟠"
    elif level_upper == "WATCH":
        return "🟡"
    else:  # INFO
        return "🔵"


def _render_alert(alert: Dict[str, Any]) -> None:
    """Helper function to render a single alert."""
    alert_id = alert.get("id")
    level = alert.get("level", "INFO")
    status = alert.get("status", "OPEN")
    color_icon = get_level_color(level)
    message = alert.get("message", "")
    timestamp = alert.get("created_at", "")
    
    # Status badge
    status_badge = {
        "OPEN": "🟢",
        "ACKED": "🟡",
        "ARCHIVED": "⚫",
    }.get(status, "⚪")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        # Create colored container based on level
        if level.upper() == "HALT":
            st.error(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        elif level.upper() == "ACTION":
            st.error(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        elif level.upper() == "WATCH":
            st.warning(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        else:  # INFO
            st.info(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
    
    with col2:
        if status == "OPEN" and alert_id:
            col_ack, col_arch = st.columns(2)
            with col_ack:
                if st.button("✓ Ack", key=f"ack_{alert_id}", use_container_width=True):
                    ack_alert(alert_id)
                    st.rerun()
            with col_arch:
                if st.button("📦 Archive", key=f"arch_{alert_id}", use_container_width=True):
                    archive_alert(alert_id)
                    st.rerun()


def _get_consecutive_zero_candidate_days() -> int:
    """Get consecutive days with 0 actionable candidates (Phase 1C).
    
    Uses ET date for consistency with heartbeat tracking.
    
    Returns
    -------
    int
        Number of consecutive days with 0 candidates.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return 0
    
    try:
        import pytz
        
        # Get ET date (not UTC) for consistency
        et_tz = pytz.timezone("America/New_York")
        et_today = datetime.now(et_tz).date()
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if tracking table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
                date TEXT PRIMARY KEY,
                candidate_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Check today's count (ET date)
        today_str = et_today.isoformat()
        cursor.execute("""
            SELECT candidate_count FROM candidate_daily_tracking
            WHERE date = ?
        """, (today_str,))
        
        row = cursor.fetchone()
        if row and row[0] == 0:
            # Count consecutive days with 0 candidates
            cursor.execute("""
                SELECT date, candidate_count
                FROM candidate_daily_tracking
                WHERE candidate_count = 0
                ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            
            # Count consecutive days from today backwards (ET dates)
            consecutive = 0
            expected_date = et_today
            
            for row in rows:
                row_date = datetime.fromisoformat(row[0]).date()
                if row_date == expected_date:
                    consecutive += 1
                    expected_date = expected_date - timedelta(days=1)
                else:
                    break
            
            conn.close()
            return consecutive
        
        conn.close()
        return 0
    except Exception:
        return 0


def _update_candidate_daily_tracking(count: int) -> None:
    """Update daily candidate count tracking (Phase 1C - ET date, upsert per day).
    
    Parameters
    ----------
    count:
        Number of actionable candidates today.
    """
    try:
        import pytz
        
        # Get ET date (not UTC) for consistency with heartbeat
        et_tz = pytz.timezone("America/New_York")
        et_now = datetime.now(et_tz)
        et_date = et_now.date().isoformat()
    except Exception:
        # Fallback to UTC if pytz not available
        et_date = datetime.now(timezone.utc).date().isoformat()
    
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
                date TEXT PRIMARY KEY,
                candidate_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Upsert (insert or replace, preserve original created_at)
        cursor.execute("""
            INSERT OR REPLACE INTO candidate_daily_tracking (date, candidate_count, created_at, updated_at)
            VALUES (?, ?, 
                COALESCE((SELECT created_at FROM candidate_daily_tracking WHERE date = ?), ?),
                ?)
        """, (et_date, count, et_date, created_at, created_at))
        
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    """Main dashboard function."""
    # DB Path Unification Fix - log DB path at startup
    from app.core.config.paths import DB_PATH
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[DASHBOARD] DB_PATH={DB_PATH.absolute()}")
    
    # Start background heartbeat (once per session)
    if not st.session_state.heartbeat_started:
        try:
            heartbeat = HeartbeatManager.get_instance()
            heartbeat.start()
            st.session_state.heartbeat_started = True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to start heartbeat: {e}")
            # Don't fail dashboard load if heartbeat fails
    
    # Header
    st.title("📊 ChakraOps Dashboard")
    st.caption("Real-time market regime and CSP candidate analysis")

    # ---- System Status Bar ----
    try:
        from app.core.market_time import get_market_state
        from app.core.market_snapshot import get_active_snapshot

        market_state = get_market_state() or {}
        regime_snapshot = get_regime_snapshot()
        last_update = get_last_update_time()
        data_mode = get_data_mode_status()

        # Market state
        m_state = market_state.get("state") or "—"

        # Regime + confidence
        if regime_snapshot:
            r_name = regime_snapshot.get("regime") or "—"
            r_conf = regime_snapshot.get("confidence")
            r_conf_str = f"{r_conf:.0f}%" if isinstance(r_conf, (int, float)) else "—"
            regime_str = f"{r_name} ({r_conf_str})"
        else:
            regime_str = "—"

        # Snapshot age
        snap = get_active_snapshot()
        if snap and snap.get("data_age_minutes") is not None:
            age_min = float(snap.get("data_age_minutes") or 0.0)
            if age_min < 60:
                snap_age = f"{age_min:.1f}m old"
            else:
                snap_age = f"{age_min/60:.1f}h old"
        else:
            snap_age = "—"

        # Data mode + ORATS health
        active_mode = data_mode.get("active_mode") or "SNAPSHOT"
        source = data_mode.get("source") or "ORATS"
        rt_health = data_mode.get("realtime_health") or "FAIL"
        mode_str = f"{active_mode} ({source} {rt_health})"

        status_line = (
            f"MARKET: {m_state} | "
            f"REGIME: {regime_str} | "
            f"SNAPSHOT: {snap_age} | "
            f"MODE: {mode_str}"
        )
        st.markdown(f"**{status_line}**")
    except Exception:
        st.markdown("**MARKET: — | REGIME: — | SNAPSHOT: — | MODE: SNAPSHOT (ORATS FAIL)**")

    # ORATS Diagnostics (on-demand, market hours)
    st.subheader("ORATS Diagnostics (Market Hours)")
    if st.button("Test ORATS Now", key="orats_diag_now", use_container_width=True):
        try:
            from app.core.options.orats_diagnostics import run_orats_diagnostic

            diag = run_orats_diagnostic("SPY")
            import logging
            _log = logging.getLogger(__name__)
            _log.info(
                "[ORATS][DIAG] run symbol=SPY state=%s is_open=%s exp_ok=%s chain_ok=%s err_type=%s err=%s",
                diag.get("market_state"),
                diag.get("is_market_open"),
                diag.get("theta_expirations_ok"),
                diag.get("theta_chain_ok"),
                diag.get("error_type"),
                diag.get("error"),
            )

            st.write(f"**Now (ET):** {diag.get('now_et')}")
            st.write(f"**Market State:** {diag.get('market_state')} | is_market_open={diag.get('is_market_open')}")

            if diag.get("error"):
                st.error(
                    f"ORATS diagnostic FAILED: {diag.get('error_type')} — {diag.get('error')}"
                )
            else:
                st.success("ORATS diagnostic PASSED for SPY")

            st.write(
                f"Expirations: ok={diag.get('theta_expirations_ok')} "
                f"count={diag.get('expirations_count')} first={diag.get('first_expiration')}"
            )
            st.write(
                f"Chain: ok={diag.get('theta_chain_ok')} count={diag.get('contracts_count')}"
            )
            st.write(
                f"Latency: expirations={diag.get('latency_ms_expirations')} ms, "
                f"chain={diag.get('latency_ms_chain')} ms"
            )

            sample = diag.get("sample_contract") or {}
            if sample:
                import pandas as pd

                st.write("Sample contract (from ORATS chain):")
                st.dataframe(
                    pd.DataFrame([sample]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No sample contract available (empty or filtered chain).")
        except Exception as e:
            st.error(f"ORATS diagnostic failed to run: {e}")

    # Data Mode / Realtime Health (detailed; snapshot remains active for decisions)
    try:
        data_mode = get_data_mode_status()
        active_mode = data_mode.get("active_mode", "SNAPSHOT")
        realtime_health = data_mode.get("realtime_health", "FAIL")
        notes = data_mode.get("notes", [])

        st.subheader("Data Mode")
        col_m, col_r = st.columns(2)
        with col_m:
            st.metric("Active Mode", active_mode, delta=None)
        with col_r:
            if realtime_health == "PASS":
                st.success(f"Realtime ({data_mode.get('source', 'ORATS')}): **{realtime_health}**")
            elif realtime_health == "WARN":
                st.warning(f"Realtime ({data_mode.get('source', 'ORATS')}): **{realtime_health}**")
            else:
                st.error(f"Realtime ({data_mode.get('source', 'THETA')}): **{realtime_health}**")

        if realtime_health == "FAIL":
            st.caption("Realtime unavailable — snapshot fallback required.")
        elif realtime_health == "PASS":
            st.caption("Realtime healthy (not yet used for decisions).")
        else:
            st.caption("Realtime partial/stale (not yet used for decisions).")

        if notes:
            with st.expander("Data Mode Details", expanded=False):
                for n in notes:
                    st.text(n)
    except Exception:
        st.subheader("Data Mode")
        st.metric("Active Mode", "SNAPSHOT", delta=None)
        st.error("Realtime (ORATS): **FAIL**")
        st.caption("Realtime unavailable — snapshot fallback required.")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controls")
        
        if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
            st.session_state.regime_cache = None
            st.session_state.candidates_cache = None
            st.rerun()
        
        st.divider()
        
        # Filters
        st.subheader("🔍 Filters")
        
        # Urgency filter
        urgency_filter = st.selectbox(
            "Urgency",
            ["ALL", "HIGH", "MEDIUM", "LOW"],
            index=0,
        )
        
        # Action filter
        action_filter = st.selectbox(
            "Action",
            ["ALL", "HOLD", "CLOSE", "ROLL", "ALERT"],
            index=0,
        )
        
        st.divider()
        
        # Last update time
        last_update = get_last_update_time()
        if last_update:
            st.metric("Last Update", last_update[:16] if len(last_update) > 16 else last_update)
        else:
            st.info("No data available")
        
        st.divider()
        
        # DEV ONLY: Reset Local Trading State
        st.subheader("⚠️ DEV Controls")
        if st.button("🗑️ Reset Local Trading State (DEV ONLY)", use_container_width=True, type="secondary"):
            st.session_state.show_reset_confirm = True
        
        if st.session_state.get("show_reset_confirm", False):
            st.warning("⚠️ This will delete all local trading data!")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Confirm Reset", use_container_width=True, type="primary"):
                    try:
                        reset_local_trading_state()
                        st.success("✅ Local trading state reset successfully!")
                        st.session_state.show_reset_confirm = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error resetting: {e}")
            with col_no:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_reset_confirm = False
                    st.rerun()
        
        st.divider()
        st.caption("ChakraOps v1.0")

    # Check if database exists
    if not db_exists():
        st.error("⚠️ Database not found")
        with st.container():
            st.info(
                """
                **Setup Instructions:**
                
                1. Make sure you have created the database by running the main application.
                2. The database should be located at: `data/chakraops.db`
                3. Run `python main.py` first to initialize the database and collect data.
                
                Once the database is created, refresh this page to see the dashboard.
                """
            )
        return

    # Portfolio Overview Section
    st.header("💼 Portfolio Overview")
    try:
        from app.core.storage.position_store import PositionStore
        from pathlib import Path
        import sqlite3
        from app.core.models.position import Position
        
        # Get all positions (for MTD calculation) - query directly from database
        all_positions = []
        try:
            db_path = get_db_path()
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        id, symbol, position_type, strike, expiry,
                        contracts, premium_collected, entry_date,
                        status, notes
                    FROM positions
                    ORDER BY entry_date DESC
                """)
                rows = cursor.fetchall()
                conn.close()
                
                # Convert rows to Position objects
                for row in rows:
                    (
                        id_, symbol, position_type, strike, expiry,
                        contracts, premium_collected, entry_date,
                        status, notes,
                    ) = row
                    all_positions.append(Position(
                        id=id_,
                        symbol=symbol,
                        position_type=position_type,  # type: ignore
                        strike=strike,
                        expiry=expiry,
                        contracts=contracts,
                        premium_collected=premium_collected,
                        entry_date=entry_date,
                        status=status,  # type: ignore
                        notes=notes,
                    ))
        except Exception:
            # Fallback to open positions only
            position_engine = PositionEngine()
            all_positions = position_engine.get_open_positions()
        
        # Get config (try to load from config.yaml or use defaults)
        config = {}
        try:
            import yaml
            config_path = Path("config.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
        except Exception:
            pass
        
        # Extract portfolio config
        portfolio_config = config.get("portfolio", {})
        target_monthly_income = portfolio_config.get("target_monthly_income", 0.0)
        
        # Compute portfolio summary
        portfolio_engine = PortfolioEngine()
        summary = portfolio_engine.compute_summary(all_positions, {"target_monthly_income": target_monthly_income})
        
        # Display portfolio overview card
        with st.container():
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Open Positions", f"{summary['open_positions']}")
            
            with col2:
                st.metric("Capital at Risk", f"${summary['capital_at_risk']:,.0f}")
            
            with col3:
                # Monthly income: actual + projected
                mtd_actual = summary['premium_collected_mtd']
                projected = summary['estimated_monthly_income']
                st.metric(
                    "Monthly Income",
                    f"${projected:,.0f}",
                    delta=f"${mtd_actual:,.0f} MTD"
                )
            
            with col4:
                # Progress badge
                progress = summary['progress_status']
                if progress == "AHEAD":
                    badge_color = "🟢"
                    badge_style = "background-color: #d4edda; color: #155724; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                elif progress == "ON_TRACK":
                    badge_color = "🟡"
                    badge_style = "background-color: #fff3cd; color: #856404; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                else:  # BEHIND
                    badge_color = "🔴"
                    badge_style = "background-color: #f8d7da; color: #721c24; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                
                st.markdown(
                    f'<div style="{badge_style}">{badge_color} {progress}</div>',
                    unsafe_allow_html=True
                )
        
        # Show target if set
        if summary['target_monthly_income'] > 0:
            st.caption(f"Target: ${summary['target_monthly_income']:,.0f}/month | Progress: {summary['progress_status']}")
    
    except Exception as e:
        st.warning(f"Unable to load portfolio overview: {e}")

    st.divider()
    
    # Portfolio Snapshot Section (Phase 1A.1 - moved here, with brokerage selector)
    st.header("💰 Portfolio Snapshot")
    
    # Brokerage selector
    brokerage_options = ["Robinhood", "Fidelity", "Charles Schwab"]
    selected_brokerage = st.selectbox(
        "Brokerage",
        brokerage_options,
        index=brokerage_options.index(st.session_state.selected_brokerage) if st.session_state.selected_brokerage in brokerage_options else 0,
        key="brokerage_selector"
    )
    st.session_state.selected_brokerage = selected_brokerage
    
    # Show latest snapshot for selected brokerage
    latest_snapshot = get_latest_portfolio_snapshot(brokerage=selected_brokerage)
    if latest_snapshot:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Account Value", f"${latest_snapshot['account_value']:,.2f}")
        with col2:
            st.metric("Cash", f"${latest_snapshot['cash']:,.2f}")
        with col3:
            invested = latest_snapshot['account_value'] - latest_snapshot['cash']
            st.metric("Invested", f"${invested:,.2f}")
        
        st.caption(f"Last updated: {latest_snapshot['timestamp'][:19] if latest_snapshot.get('timestamp') else 'N/A'}")
        if latest_snapshot.get('notes'):
            st.info(f"Notes: {latest_snapshot['notes']}")
    else:
        st.info(f"No snapshot found for {selected_brokerage}. Create one below.")
    
    # Snapshot input form
    with st.expander("📝 Update Portfolio Snapshot", expanded=False):
        with st.form("portfolio_snapshot_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                account_value = st.number_input("Account Value ($)", value=latest_snapshot['account_value'] if latest_snapshot else 0.0, step=100.0)
                cash = st.number_input("Cash ($)", value=latest_snapshot['cash'] if latest_snapshot else 0.0, step=100.0)
            
            with col2:
                timestamp = st.text_input("Timestamp (ISO)", value=datetime.now(timezone.utc).isoformat())
                notes = st.text_area("Notes (optional)", value="")
            
            submit_snapshot = st.form_submit_button("💾 Save Snapshot", use_container_width=True, type="primary")
            
            if submit_snapshot:
                try:
                    snapshot_id = save_portfolio_snapshot(
                        account_value=account_value,
                        cash=cash,
                        brokerage=selected_brokerage,
                        timestamp=timestamp if timestamp else None,
                        notes=notes if notes else None,
                    )
                    st.success(f"✅ Snapshot saved! ID: {snapshot_id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error saving snapshot: {e}")

    st.divider()

    # Heartbeat Health Panel (Phase 1D - Hardened)
    heartbeat = HeartbeatManager.get_instance()
    health = heartbeat.get_health()
    
    with st.expander("💓 Heartbeat Health", expanded=False):
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        
        with col_h1:
            if health["last_cycle_time"]:
                last_cycle = datetime.fromisoformat(health["last_cycle_time"])
                age_seconds = (datetime.now(timezone.utc) - last_cycle).total_seconds()
                if age_seconds < 120:
                    st.metric("Status", "🟢 Running", delta=f"{int(age_seconds)}s ago")
                else:
                    st.metric("Status", "🟡 Stale", delta=f"{int(age_seconds/60)}m ago")
            else:
                st.metric("Status", "⚪ Unknown", delta="No cycles")
        
        with col_h2:
            status = health["status"]
            status_icon = {
                "SUCCESS": "✅",
                "ERROR": "❌",
                "NO_REGIME": "⚠️",
                "NO_DATA": "⚠️",
                "NO_SNAPSHOT": "⚠️",
                "REGIME_STALE": "🟡",
            }.get(status, "⚪")
            st.metric("Last Cycle", f"{status_icon} {status}")
        
        with col_h3:
            if health["data_timestamp"]:
                data_time = datetime.fromisoformat(health["data_timestamp"])
                data_age_minutes = (datetime.now(timezone.utc) - data_time).total_seconds() / 60.0
                if data_age_minutes < 5:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Fresh")
                elif data_age_minutes < 15:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Stale", delta_color="off")
                else:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Very Stale", delta_color="inverse")
            else:
                st.metric("Data Age", "N/A")
        
        with col_h4:
            if health["last_error"]:
                st.error(f"❌ {health['last_error'][:50]}")
            else:
                st.success("✅ No errors")
        
        if health["is_running"]:
            st.caption("🟢 Heartbeat thread is running")
        else:
            st.warning("⚠️ Heartbeat thread is not running")
    
    # Heartbeat Evaluation Debug Panel
    eval_details = heartbeat.get_cycle_eval_details()
    
    with st.expander("🔍 Heartbeat Evaluation Debug", expanded=False):
        if health["last_cycle_time"]:
            last_cycle = datetime.fromisoformat(health["last_cycle_time"])
            # Convert to ET for display
            try:
                import pytz
                et_tz = pytz.timezone("America/New_York")
                if last_cycle.tzinfo is None:
                    last_cycle = pytz.UTC.localize(last_cycle)
                last_cycle_et = last_cycle.astimezone(et_tz)
                cycle_time_str = last_cycle_et.strftime("%Y-%m-%d %H:%M:%S %Z")
            except Exception:
                cycle_time_str = last_cycle.strftime("%Y-%m-%d %H:%M:%S UTC")
            
            col_e1, col_e2, col_e3 = st.columns(3)
            
            with col_e1:
                st.metric("Last Cycle Time (ET)", cycle_time_str)
                st.metric("Symbols Evaluated", eval_details.get("symbols_evaluated", 0))
                st.metric("Enabled Universe Size", eval_details.get("enabled_universe_size", 0))
            
            with col_e2:
                st.metric("CSP Candidates Found", eval_details.get("csp_candidates_count", 0))
                st.metric("Rejected Symbols", eval_details.get("rejected_symbols_count", 0))
                market_age = eval_details.get("market_data_age_minutes", 0.0)
                if market_age < 5:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Fresh")
                elif market_age < 15:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Stale", delta_color="off")
                else:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Very Stale", delta_color="inverse")
            
            with col_e3:
                rejection_reasons = eval_details.get("rejection_reasons", {})
                if rejection_reasons:
                    st.write("**Top Rejection Reasons:**")
                    # Sort by count, get top 3
                    sorted_reasons = sorted(
                        rejection_reasons.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]
                    for reason, count in sorted_reasons:
                        st.write(f"- {reason}: {count}")
                else:
                    st.write("**Top Rejection Reasons:**")
                    st.caption("No rejections recorded")
        else:
            st.info("No cycle evaluation data available yet. Heartbeat may not have completed a cycle.")
    
    # Market Snapshot Panel (Phase 2A)
    from app.core.market_snapshot import get_active_snapshot, build_market_snapshot, load_snapshot_data, normalize_symbol
    from app.core.persistence import get_enabled_symbols
    
    # Reload snapshot explicitly (refresh after build)
    snapshot = get_active_snapshot()
    with st.expander("📸 Market Snapshot", expanded=False):
        if snapshot:
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            
            with col_s1:
                try:
                    import pytz
                    et_tz = pytz.timezone("America/New_York")
                    snapshot_time = datetime.fromisoformat(snapshot["snapshot_timestamp_et"])
                    if snapshot_time.tzinfo is None:
                        snapshot_time = pytz.UTC.localize(snapshot_time)
                    snapshot_time_et = snapshot_time.astimezone(et_tz)
                    snapshot_str = snapshot_time_et.strftime("%Y-%m-%d %H:%M:%S %Z")
                except Exception:
                    snapshot_str = snapshot["snapshot_timestamp_et"]
                st.metric("Snapshot Time (ET)", snapshot_str)
            
            with col_s2:
                # Extract source from provider field
                provider = snapshot.get("provider", "snapshot")
                source = "UNKNOWN"
                if "csv" in provider.lower():
                    source = "CSV"
                elif "cache" in provider.lower():
                    source = "CACHE"
                else:
                    source = "SNAPSHOT"
                st.metric("Mode", "SNAPSHOT", delta=f"Source: {source}")
            
            with col_s3:
                # Calculate coverage: normalized(snapshot_symbols) ∩ normalized(enabled_universe_symbols)
                snapshot_data = load_snapshot_data(snapshot["snapshot_id"])
                snapshot_symbols_normalized = {normalize_symbol(s) for s in snapshot_data.keys()}
                
                enabled_symbols = get_enabled_symbols()
                enabled_symbols_normalized = {normalize_symbol(s) for s in enabled_symbols}
                
                # Intersection = covered symbols
                covered_symbols = snapshot_symbols_normalized & enabled_symbols_normalized
                symbols_with_data = len([v for s, v in snapshot_data.items() if normalize_symbol(s) in covered_symbols and v is not None])
                
                st.metric(
                    "Symbols Covered",
                    f"{len(covered_symbols)}/{len(enabled_symbols_normalized)}",
                    delta=f"{len(enabled_symbols_normalized) - len(covered_symbols)} missing"
                )
            
            with col_s4:
                age_minutes = snapshot.get("data_age_minutes", 0.0)
                age_hours = age_minutes / 60.0
                if age_hours < 1:
                    age_str = f"{age_minutes:.1f}m"
                else:
                    age_str = f"{age_hours:.1f}h"
                st.metric("Snapshot Age", age_str)
            # Benchmarks presence (display only)
            _snap_syms = {normalize_symbol(s) for s in snapshot_data.keys()}
            _spy_ok = normalize_symbol("SPY") in _snap_syms
            _qqq_ok = normalize_symbol("QQQ") in _snap_syms
            if _spy_ok and _qqq_ok:
                st.caption("Benchmarks present: SPY, QQQ")
            else:
                st.caption("Benchmarks missing")
        else:
            st.warning("⚠️ No active snapshot available. Build a snapshot to enable evaluation.")
        
        # DEV-only: Seed Snapshot from fixture (no yfinance). Writes market_snapshot.csv from eod_seed.csv.
        _dev_mode = os.environ.get("CHAKRAOPS_DEV", "").lower() in ("1", "true", "yes")
        if _dev_mode:
            if st.button("🌱 Seed Snapshot from Last Close (DEV)", use_container_width=True, type="secondary"):
                try:
                    from app.core.dev_seed import seed_snapshot_from_fixture
                    path, count = seed_snapshot_from_fixture()
                    st.success(f"✅ Seeded {count} symbols to {path.name}. Click **Build New Snapshot** to ingest.")
                    st.rerun()
                except FileNotFoundError as e:
                    st.error(
                        f"❌ Fixture missing: {e}\n\n"
                        "**Steps:**\n"
                        "1. Run: `python tools/generate_eod_seed_fixture.py`\n"
                        "2. Or create `app/data/fixtures/eod_seed.csv` with columns: symbol, price, volume, iv_rank, timestamp (ET ISO)\n"
                        "3. Then click this button again."
                    )
                except Exception as e:
                    st.error(f"❌ Seed failed: {e}")
        
        # DB path hint when multiple DBs exist (deterministic rebuild clarity)
        try:
            from app.core.config.paths import DB_PATH
            _data_dir = DB_PATH.parent
            if _data_dir.exists():
                _db_files = list(_data_dir.glob("*.db"))
                if len(_db_files) > 1:
                    st.caption(f"⚠️ Multiple DB files in {_data_dir.name}/ — using: **{str(DB_PATH)}**")
        except Exception:
            pass
        
        # Build snapshot button: always rebuild from current market_snapshot.csv, then run one heartbeat cycle
        if st.button("🔨 Build New Snapshot", use_container_width=True, type="primary"):
            with st.spinner("Building market snapshot from current CSV, then running evaluation..."):
                try:
                    result = build_market_snapshot(mode="CSV")
                    source = result.get("source", "UNKNOWN")
                    st.success(
                        f"✅ Snapshot built! "
                        f"ID: {result['snapshot_id'][:8]}... | "
                        f"Source: {source} | "
                        f"Symbols: {result['symbols_with_data']}/{result['symbol_count']} with data"
                    )
                    try:
                        HeartbeatManager.get_instance().run_one_cycle()
                    except Exception as _e:
                        import logging
                        logging.getLogger(__name__).warning("Heartbeat cycle after build failed: %s", _e)
                    st.rerun()
                except ValueError as e:
                    msg = str(e)
                    if "CSV" in msg or "csv" in msg.lower():
                        st.error(f"❌ {msg}\n\n**Hint:** Run **Seed Snapshot from Last Close (DEV)** first, or `python tools/generate_eod_seed_fixture.py`.")
                    else:
                        st.error(f"❌ {msg}")
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[DASHBOARD] Snapshot build ValueError: {e}")
                except Exception as e:
                    # Step 2: Show clear error message with logging
                    error_msg = str(e)
                    st.error(f"❌ Failed to build snapshot: {error_msg}")
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[DASHBOARD] Snapshot build error: {error_msg}", exc_info=True)
    
    st.divider()

    # ---- Today’s Action (Top CSP candidates) ----
    st.divider()
    st.header("🎯 Today’s Action")
    st.caption("Top opportunities based on latest snapshot. Review → decide → act.")

    from app.core.market_snapshot import get_active_snapshot
    from app.core.persistence import get_csp_evaluations, get_rejection_reason_counts

    snapshot = get_active_snapshot()
    if snapshot:
        snapshot_id = snapshot["snapshot_id"]
        _evals = get_csp_evaluations(snapshot_id)
        _eligible = [e for e in _evals if e.get("eligible")]
        _eligible.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_csp = _eligible[:3]
        if top_csp:
            for e in top_csp:
                symbol = e.get("symbol", "?")
                score = e.get("score", 0)
                features = e.get("features", {}) or {}
                short_reason = features.get("assignment_label") or "Snapshot-qualified CSP candidate"
                status_key = f"todays_action_status_{symbol}_CSP"
                if status_key not in st.session_state:
                    st.session_state[status_key] = "New"

                with st.container():
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"### {symbol} · CSP")
                        st.metric("Score", f"{score}/100")
                        st.caption(short_reason)
                    with col2:
                        st.caption(f"Status: {st.session_state[status_key]}")
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button("Reviewed", key=f"ta_review_{symbol}"):
                                st.session_state[status_key] = "Reviewed"
                        with b2:
                            if st.button("Open", key=f"ta_open_{symbol}"):
                                # Reuse existing execution form via record_execution_modal
                                st.session_state.record_execution_modal = symbol
                        with b3:
                            if st.button("Ignore", key=f"ta_ignore_{symbol}"):
                                st.session_state[status_key] = "Ignored"
        else:
            st.caption("No eligible CSP candidates for today.")
    else:
        st.caption("No active snapshot; build a snapshot to see today's action.")

    # Daily Trading Plan Card (Phase 1C)
    st.header("📋 Daily Trading Plan")
    
    # Get actionable candidates (not blocked, not executed)
    actionable_candidates = []
    has_error = False
    error_message = ""
    
    try:
        # Use csp_evaluations instead of legacy csp_candidates
        from app.core.market_snapshot import get_active_snapshot
        from app.core.persistence import get_csp_evaluations
        snapshot = get_active_snapshot()
        if snapshot:
            evaluations = get_csp_evaluations(snapshot["snapshot_id"])
            all_candidates = [e for e in evaluations if e.get("eligible", False)]
        else:
            all_candidates = []
        actionable_candidates = [
            c for c in all_candidates
            if not c.get("blocked", False) or c.get("operator_override", False)
        ]
    except Exception as e:
        has_error = True
        error_message = str(e)
        actionable_candidates = []
    
    # Determine plan status
    if has_error:
        plan_status = "HALT"
        plan_message = f"System halted — data unavailable: {error_message}"
        plan_color = "#721c24"
        plan_bg = "#f8d7da"
        plan_icon = "🛑"
    elif len(actionable_candidates) > 0:
        plan_status = "ACTIONABLE"
        plan_message = f"{len(actionable_candidates)} CSP opportunity{'ies' if len(actionable_candidates) != 1 else 'y'} available"
        plan_color = "#155724"
        plan_bg = "#d4edda"
        plan_icon = "✅"
    else:
        plan_status = "INFO"
        plan_message = "No trades today — conditions not favorable"
        plan_color = "#856404"
        plan_bg = "#fff3cd"
        plan_icon = "ℹ️"
    
    # Display plan card
    st.markdown(
        f"""
        <div style="background-color: {plan_bg}; color: {plan_color}; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h2 style="margin: 0; color: {plan_color};">
                {plan_icon} {plan_status}
            </h2>
            <p style="margin: 10px 0 0 0; color: {plan_color}; font-size: 16px;">
                {plan_message}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Universe Guidance (Phase 1C) - Track consecutive days with 0 candidates
    if len(actionable_candidates) == 0 and not has_error:
        # Check consecutive days with 0 candidates
        consecutive_days = _get_consecutive_zero_candidate_days()
        if consecutive_days >= 2:
            st.info(
                f"📊 No opportunities found for {consecutive_days} consecutive days. "
                "Consider expanding your symbol universe. See Universe Manager section below."
            )
    
    st.divider()

    # Market Regime Section - Large Status Card
    st.header("📈 Market Regime")

    # Snapshot (Authoritative) - only source used for decisions
    st.caption("**Snapshot (Authoritative)**")
    regime = get_regime_snapshot()

    # Check regime freshness (Phase 1D)
    regime_stale_warning = None
    if regime:
        try:
            created_at_str = regime.get("created_at")
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str)
                age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0
                if age_minutes > REGIME_STALE_THRESHOLD_MINUTES:
                    regime_stale_warning = f"⚠️ Regime data is {age_minutes:.1f} minutes old (stale threshold: {REGIME_STALE_THRESHOLD_MINUTES} min)"
        except Exception:
            pass
    
    if regime:
        # Large status card
        is_risk_on = regime["regime"] == "RISK_ON"
        status_color = "🟢" if is_risk_on else "🔴"
        status_bg = "background-color: #d4edda; padding: 20px; border-radius: 10px;" if is_risk_on else "background-color: #f8d7da; padding: 20px; border-radius: 10px;"
        
        with st.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(
                    f"""
                    <div style="{status_bg}">
                        <h2 style="margin: 0; color: {'#155724' if is_risk_on else '#721c24'};">
                            {status_color} {regime['regime']}
                        </h2>
                        <p style="margin: 5px 0 0 0; color: {'#155724' if is_risk_on else '#721c24'};">
                            Confidence: {regime['confidence']}%
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col2:
                st.metric("Confidence", f"{regime['confidence']}%")
            
            with col3:
                if regime.get("created_at"):
                    update_time = regime["created_at"][:16] if len(regime["created_at"]) > 16 else regime["created_at"]
                    st.metric("Updated", update_time)
        
        # Regime freshness warning (Phase 1D)
        if regime_stale_warning:
            st.warning(regime_stale_warning)
        
        # Details expander
        with st.expander("📋 View Detailed Metrics", expanded=False):
            st.json(regime.get("details", {}))
    else:
        st.warning("⚠️ No regime data available. Run the main application to collect regime snapshots.")

    # Realtime Regime (Shadow) - read-only, not used for decisions
    st.subheader("Realtime Regime (Shadow)")
    shadow = get_shadow_realtime_regime()
    if shadow is None:
        st.info("Realtime regime unavailable")
    else:
        health = shadow.get("realtime_health", "WARN")
        conf = shadow.get("confidence")
        conf_pct = f"{int(round(conf * 100))}%" if conf is not None else "—"
        rg = shadow.get("regime", "—")
        with st.container():
            rc, cc, hc = st.columns([2, 1, 1])
            with rc:
                st.markdown(
                    f"""
                    <div style="background-color: #f8f9fa; color: #6c757d; padding: 14px; border-radius: 8px; border: 1px solid #dee2e6;">
                        <p style="margin: 0; font-size: 18px; color: #6c757d;">{rg}</p>
                        <p style="margin: 4px 0 0 0; font-size: 14px; color: #6c757d;">Confidence: {conf_pct}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with cc:
                st.metric("Confidence", conf_pct)
            with hc:
                if health == "PASS":
                    st.success(f"**{health}**")
                else:
                    st.warning(f"**{health}**")
        st.caption("Shadow evaluation — not used for decisions.")

    st.divider()

    # ---- Candidate Explorer (Full list) ----
    with st.expander("📋 Candidate Explorer (Full List)", expanded=False):
        from app.core.market_snapshot import get_active_snapshot
        from app.core.persistence import get_csp_evaluations, get_rejection_reason_counts

        snapshot = get_active_snapshot()
        if snapshot:
            snapshot_id = snapshot["snapshot_id"]
            evaluations = get_csp_evaluations(snapshot_id)
            rejection_reasons = get_rejection_reason_counts(snapshot_id)

            # Filter to eligible only and sort by score desc
            eligible_evaluations = [e for e in evaluations if e["eligible"]]
            eligible_evaluations.sort(key=lambda x: x["score"], reverse=True)

            with st.expander("📊 Candidate Summary", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("CSP Candidates Found", len(eligible_evaluations))
                with col2:
                    rejected_count = len([e for e in evaluations if not e["eligible"]])
                    st.metric("Rejected Symbols", rejected_count)
                with col3:
                    if rejection_reasons:
                        top_reason = rejection_reasons[0][0]
                        top_count = rejection_reasons[0][1]
                        st.metric("Top Rejection Reason", f"{top_reason} ({top_count})")

                if rejection_reasons:
                    with st.expander("Top Rejection Reasons (detail)", expanded=False):
                        for reason, count in rejection_reasons[:5]:
                            st.write(f"- **{reason}**: {count} symbols")

            # Options rejection details (Phase 5): options-layer rejection reasons and debug_inputs
            _opts_rejected = [
                e
                for e in evaluations
                if e.get("features", {}).get("options_rejection_reasons")
                or e.get("features", {}).get("options_debug_inputs")
            ]
            if _opts_rejected:
                with st.expander("🔬 Options rejection details", expanded=False):
                    for e in _opts_rejected:
                        sym = e.get("symbol", "?")
                        reasons = e.get("features", {}).get("options_rejection_reasons") or []
                        debug = e.get("features", {}).get("options_debug_inputs") or {}
                        st.write(f"**{sym}**")
                        if reasons:
                            st.caption(f"Options rejection reasons: {', '.join(reasons)}")
                        if debug:
                            st.json(debug)
                        st.divider()

            # Why symbols were rejected: per-symbol eval details (price, volume, iv_rank, regime, snapshot_age_minutes)
            with st.expander("🔍 Why symbols were rejected", expanded=False):
                for e in evaluations:
                    sym = e.get("symbol", "?")
                    elig = e.get("eligible", False)
                    score = e.get("score", 0)
                    reasons = e.get("rejection_reasons", [])
                    feat = e.get("features", {})
                    rctx = e.get("regime_context", {})
                    price = feat.get("price")
                    volume = feat.get("volume")
                    iv_rank = feat.get("iv_rank")
                    snapshot_age_minutes = feat.get("snapshot_age_minutes")
                    regime = rctx.get("regime", "?")
                    st.write(
                        f"**{sym}** | eligible={elig} | score={score} | "
                        f"price={price} | volume={volume} | iv_rank={iv_rank} | "
                        f"regime={regime} | snapshot_age_min={snapshot_age_minutes}"
                    )
                    if reasons:
                        st.caption(f"Rejection reasons: {', '.join(reasons)}")
                    st.divider()

            # Update daily tracking (Phase 1C)
            _update_candidate_daily_tracking(len(eligible_evaluations))

            # Display eligible candidates
            if eligible_evaluations:
                # Top candidate highlight
                if len(eligible_evaluations) > 0:
                    top_eval = eligible_evaluations[0]
                    with st.container():
                        st.success(
                            f"🏆 **Top Candidate: {top_eval['symbol']}** "
                            f"| Score: **{top_eval['score']}/100**"
                        )

                st.write("")  # Spacing

                # Candidate cards with "Why?" expanders
                for i, eval_result in enumerate(eligible_evaluations, 1):
                    symbol = eval_result["symbol"]
                    score = eval_result["score"]
                    features = eval_result.get("features", {})
                    regime_context = eval_result.get("regime_context", {})
                    rejection_reasons = eval_result.get("rejection_reasons", [])

                    with st.container():
                        # Score badge color
                        if score >= 80:
                            badge_color = "🟢"
                        elif score >= 60:
                            badge_color = "🟡"
                        else:
                            badge_color = "🟠"

                        # Main candidate card
                        col1, col2, col3 = st.columns([1, 2, 1])

                        with col1:
                            st.markdown(f"### {badge_color} {symbol}")
                            st.metric("CSP Score", f"{score}/100")

                        with col2:
                            price = features.get("price", "N/A")
                            volume = features.get("volume")
                            iv_rank = features.get("iv_rank")
                            snapshot_age = features.get("snapshot_age_minutes", 0)
                            regime = regime_context.get("regime", "UNKNOWN")

                            st.write("**Details:**")
                            cols = st.columns(5)
                            with cols[0]:
                                st.metric("Price", f"${price:.2f}" if isinstance(price, (int, float)) else str(price))
                            with cols[1]:
                                st.metric("Regime", regime)
                            with cols[2]:
                                age_str = f"{snapshot_age:.1f}m" if snapshot_age < 60 else f"{snapshot_age/60:.1f}h"
                                st.metric("Data Age", age_str)
                            with cols[3]:
                                if volume is not None:
                                    vol_str = f"{volume/1_000_000:.1f}M" if volume >= 1_000_000 else f"{volume/1_000:.1f}K"
                                    st.metric("Volume", vol_str)
                                else:
                                    st.metric("Volume", "N/A")
                            with cols[4]:
                                if iv_rank is not None:
                                    st.metric("IV Rank", f"{iv_rank:.1f}")
                                else:
                                    st.metric("IV Rank", "N/A")

                            # Chosen Contract (Phase 5): expiry, strike, delta, mid, roc, spread_pct
                            chosen = features.get("chosen_contract")
                            if chosen:
                                st.write("**Chosen Contract:**")
                                cc_cols = st.columns(6)
                                with cc_cols[0]:
                                    st.metric("Expiry", str(chosen.get("expiry", "—"))[:10])
                                with cc_cols[1]:
                                    st.metric("Strike", f"${chosen.get('strike', 0):.2f}" if chosen.get("strike") is not None else "—")
                                with cc_cols[2]:
                                    d = chosen.get("delta")
                                    st.metric("Delta", f"{d:.2f}" if d is not None else "—")
                                with cc_cols[3]:
                                    m = chosen.get("mid")
                                    st.metric("Mid", f"${m:.2f}" if m is not None else "—")
                                with cc_cols[4]:
                                    roc = features.get("options_roc")
                                    st.metric("ROC", f"{roc*100:.2f}%" if roc is not None else "—")
                                with cc_cols[5]:
                                    sp = features.get("options_spread_pct")
                                    st.metric("Spread %", f"{sp:.1f}%" if sp is not None else "—")

                        with col3:
                            # "Why?" expander (Phase 2B Step 3)
                            with st.expander("❓ Why?", expanded=False):
                                st.write("**Score Breakdown:**")
                                score_components = features.get("score_components", {})
                                if score_components:
                                    for component, value in score_components.items():
                                        st.write(f"- {component.replace('_', ' ').title()}: {value:.1f}")
                                else:
                                    st.write("No score components available")

                                st.divider()

                                # Display volume and IV rank explicitly (Phase 2B Step 3)
                                st.write("**Market Data:**")
                                col_data1, col_data2 = st.columns(2)
                                with col_data1:
                                    vol = features.get("volume")
                                    if vol is not None:
                                        vol_str = f"{vol/1_000_000:.2f}M" if vol >= 1_000_000 else f"{vol/1_000:.2f}K"
                                        st.write(f"Volume: {vol_str}")
                                    else:
                                        st.write("Volume: N/A")
                                with col_data2:
                                    iv = features.get("iv_rank")
                                    if iv is not None:
                                        st.write(f"IV Rank: {iv:.1f}")
                                    else:
                                        st.write("IV Rank: N/A")

                                # Show which gate failed (if rejected)
                                if rejection_reasons:
                                    st.divider()
                                    st.write("**Rejection Reasons:**")
                                    for reason in rejection_reasons:
                                        if reason == "low_liquidity":
                                            st.error(f"❌ {reason}: Volume < 1M (current: {vol/1_000_000:.2f}M)" if vol is not None else f"❌ {reason}: Volume < 1M")
                                        elif reason == "iv_too_low":
                                            st.error(f"❌ {reason}: IV Rank < 20 (current: {iv:.1f})" if iv is not None else f"❌ {reason}: IV Rank < 20")
                                        else:
                                            st.write(f"- {reason}")

                                st.divider()
                                st.write("**All Features:**")
                                st.json(features)

                                st.write("**Regime Context:**")
                                st.json(regime_context)

                        st.divider()
            else:
                st.info("📭 No eligible CSP candidates found. Check rejection reasons above.")
        else:
            st.warning("⚠️ No active snapshot available. Build a snapshot to enable evaluation.")

            # No fallback - csp_candidates table removed, only csp_evaluations exists
            st.info("📭 No CSP candidates found. Build a snapshot and wait for heartbeat evaluation.")

    st.divider()
    
    # Record Execution Modal
    if st.session_state.record_execution_modal:
        candidate_symbol = st.session_state.record_execution_modal
        # Find candidate details (from evaluations or legacy candidates)
        candidate_details = None
        if snapshot:
            evaluations = get_csp_evaluations(snapshot["snapshot_id"])
            for e in evaluations:
                if e['symbol'] == candidate_symbol:
                    candidate_details = e
                    break
        if not candidate_details:
            # No fallback - csp_candidates table removed
            candidate_details = None
        
        if candidate_details:
            contract = candidate_details.get("contract", {})
            with st.container():
                st.header("📝 Record Trade Execution")
                
                with st.form(f"record_trade_form_{candidate_symbol}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        symbol = st.text_input("Symbol", value=candidate_symbol, disabled=True)
                        strike = st.number_input("Strike", value=float(contract.get('strike', 0)) if contract.get('strike') else 0.0, step=0.5)
                        expiry = st.text_input("Expiry (YYYY-MM-DD)", value=contract.get('expiry', ''))
                        contracts = st.number_input("Contracts", value=1, min_value=1, step=1)
                    
                    with col2:
                        premium = st.number_input("Premium Collected ($)", value=float(contract.get('premium_estimate', 0)) if contract.get('premium_estimate') else 0.0, step=0.01)
                        timestamp = st.text_input("Timestamp (ISO)", value=datetime.now(timezone.utc).isoformat())
                        notes = st.text_area("Notes (optional)", value="")
                    
                    # Capital Impact Preview (Phase 1C)
                    if strike > 0 and contracts > 0:
                        required_cash = strike * contracts * 100
                        
                        # Get available cash from latest snapshot
                        latest_snapshot = get_latest_portfolio_snapshot(brokerage=st.session_state.selected_brokerage)
                        available_cash = latest_snapshot.get('cash', 0.0) if latest_snapshot else 0.0
                        
                        cash_percentage = (required_cash / available_cash * 100) if available_cash > 0 else 0
                        
                        st.divider()
                        st.write("**💰 Capital Impact Preview:**")
                        col_cash1, col_cash2 = st.columns(2)
                        with col_cash1:
                            st.metric("Required Cash", f"${required_cash:,.2f}")
                        with col_cash2:
                            st.metric("Available Cash", f"${available_cash:,.2f}")
                        
                        # Warnings
                        if available_cash > 0:
                            if required_cash > available_cash:
                                st.error(f"❌ **Insufficient Cash:** Required ${required_cash:,.2f} exceeds available ${available_cash:,.2f}")
                                execution_disabled = True
                            elif cash_percentage > 25:
                                st.warning(f"⚠️ **High Cash Usage:** {cash_percentage:.1f}% of available cash")
                                execution_disabled = False
                            else:
                                st.success(f"✅ **Cash Available:** {cash_percentage:.1f}% of available cash")
                                execution_disabled = False
                        else:
                            st.warning("⚠️ **No Cash Data:** Update portfolio snapshot to see cash impact")
                            execution_disabled = False
                        
                        st.divider()
                    else:
                        execution_disabled = False
                    
                    # Market-time awareness (Phase 1C)
                    market_state = get_market_state()
                    market_is_open = is_market_open()
                    
                    if not market_is_open:
                        if market_state == "WEEKEND":
                            st.info("⏸️ **Market Closed:** Weekend. Execution disabled.")
                        elif market_state == "PRE_MARKET":
                            st.info("⏸️ **Market Closed:** Pre-market. Market opens at 9:30 AM ET.")
                        else:
                            st.info("⏸️ **Market Closed:** After hours. Execution disabled.")
                        execution_disabled = True
                    
                    col_submit, col_cancel = st.columns(2)
                    with col_submit:
                        submit = st.form_submit_button(
                            "💾 Save Trade",
                            use_container_width=True,
                            type="primary",
                            disabled=execution_disabled
                        )
                    with col_cancel:
                        cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
                    
                    if submit and not execution_disabled:
                        try:
                            # Record trade
                            trade_id = record_trade(
                                symbol=symbol,
                                action="SELL_TO_OPEN",
                                strike=strike if strike > 0 else None,
                                expiry=expiry if expiry else None,
                                contracts=contracts,
                                premium=premium,
                                timestamp=timestamp if timestamp else None,
                                notes=notes if notes else None,
                            )
                            
                            # Create position from trade
                            position = upsert_position_from_trade(trade_id)
                            
                            # Mark candidate as executed
                            mark_candidate_executed(symbol, executed=True)
                            
                            # Clear cache and modal
                            st.session_state.candidates_cache = None
                            st.session_state.record_execution_modal = None
                            
                            st.success(f"✅ Trade recorded! Position created: {position.id if position else 'N/A'}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error recording trade: {e}")
                    
                    if cancel:
                        st.session_state.record_execution_modal = None
                        st.rerun()
    
    st.divider()

    # ---- Positions ----
    st.header("📂 Positions")

    # Active Positions Section (Phase 1A) - Open Positions summary
    st.subheader("Open Positions")
    try:
        open_positions = persistence_list_open_positions()
        
        if open_positions:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            total_contracts = sum(p.contracts for p in open_positions)
            total_premium = sum(p.premium_collected for p in open_positions)
            unique_symbols = len(set(p.symbol for p in open_positions))
            
            with col1:
                st.metric("Open Positions", len(open_positions))
            with col2:
                st.metric("Total Contracts", total_contracts)
            with col3:
                st.metric("Total Premium", f"${total_premium:,.2f}")
            with col4:
                st.metric("Unique Symbols", unique_symbols)
            
            st.write("")  # Spacing
            
            # Positions table
            positions_data = []
            for pos in open_positions:
                avg_credit = pos.premium_collected / pos.contracts if pos.contracts > 0 else 0
                positions_data.append({
                    "Symbol": pos.symbol,
                    "Strike": f"${pos.strike:.2f}" if pos.strike else "N/A",
                    "Expiry": pos.expiry or "N/A",
                    "Contracts": pos.contracts,
                    "Avg Credit": f"${avg_credit:.2f}",
                    "Total Premium": f"${pos.premium_collected:.2f}",
                    "Status": pos.state or pos.status,
                    "Entry Date": pos.entry_date[:10] if pos.entry_date else "N/A",
                })
            
            df_positions = pd.DataFrame(positions_data)
            st.dataframe(df_positions, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions.")
    except Exception as e:
        st.warning(f"Unable to load positions: {e}")

    st.divider()

    # Today's Focus Card (HIGH urgency count)
    try:
        position_engine = PositionEngine()
        all_open_positions = position_engine.get_open_positions()
        
        # Quick count of HIGH urgency (without full evaluation)
        high_urgency_count = 0
        if all_open_positions:
            regime_snapshot = get_regime_snapshot()
            regime_value = regime_snapshot.get("regime") if regime_snapshot else "RISK_OFF"
            
            try:
                from app.data.yfinance_provider import YFinanceProvider
                price_provider = YFinanceProvider()
            except Exception:
                price_provider = None
            
            for pos in all_open_positions:
                try:
                    market_ctx = {"regime": regime_value}
                    if price_provider:
                        try:
                            df = price_provider.get_daily(pos.symbol, lookback=250)
                            if not df.empty:
                                df = df.sort_values("date", ascending=True).reset_index(drop=True)
                                latest = df.iloc[-1]
                                market_ctx["underlying_price"] = float(latest["close"])
                        except Exception:
                            pass
                    
                    # Use new action engine
                    decision = evaluate_position_action(pos, market_ctx)
                    if decision and decision.urgency == "HIGH":
                        high_urgency_count += 1
                except Exception:
                    pass
    except Exception:
        high_urgency_count = 0
    
    # Today's Focus Card
    if high_urgency_count > 0:
        with st.container():
            st.markdown(
                f"""
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: #856404;">🎯 Today's Focus</h3>
                    <p style="margin: 5px 0 0 0; color: #856404; font-size: 18px; font-weight: bold;">
                        {high_urgency_count} HIGH Urgency Alert{'s' if high_urgency_count != 1 else ''}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # Open Positions Section - Historical / Reviewed positions
    st.subheader("Historical / Reviewed Positions")
    try:
        position_engine = PositionEngine()
        open_positions = position_engine.get_open_positions()
    except Exception as e:
        st.warning(f"Unable to load positions: {e}")
        open_positions = []

    if open_positions:
        # Get regime for market context
        regime_snapshot = get_regime_snapshot()
        regime_value = regime_snapshot.get("regime") if regime_snapshot else "RISK_OFF"
        
        # Get price provider for fetching current prices
        try:
            from app.data.yfinance_provider import YFinanceProvider
            price_provider = YFinanceProvider()
        except Exception:
            price_provider = None
        
        position_data = []
        
        for position in open_positions:
            # Build market context for Action Engine
            market_context = {"regime": regime_value}
            
            # Fetch current price, EMA200, EMA50 if provider available
            if price_provider:
                try:
                    df = price_provider.get_daily(position.symbol, lookback=250)
                    if not df.empty:
                        df = df.sort_values("date", ascending=True).reset_index(drop=True)
                        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
                        latest = df.iloc[-1]
                        current_price = float(latest["close"])
                        market_context["underlying_price"] = current_price
                        market_context["current_price"] = current_price
                        market_context["EMA200"] = float(latest["ema200"])
                        market_context["EMA50"] = float(latest["ema50"])
                        market_context["price"] = current_price
                        market_context["price_df"] = df
                        
                        # Calculate ATR proxy (3% default)
                        market_context["ATR_pct"] = 0.03
                        
                        # Calculate premium collected percentage
                        if position.strike and position.strike > 0 and position.contracts > 0:
                            premium_per_contract = position.premium_collected / position.contracts
                            premium_pct = (premium_per_contract / (position.strike * 100)) * 100
                            market_context["premium_collected_pct"] = premium_pct
                except Exception:
                    pass  # Continue without price data
            
            # Evaluate position with Action Engine (new Week 4 Day 2 engine)
            action_decision = None
            try:
                action_decision = evaluate_position_action(position, market_context)
            except Exception as e:
                # Fallback to basic decision if Action Engine fails
                action_decision = None
            
            position_data.append({
                "position": position,
                "action_decision": action_decision,
                "market_context": market_context,
            })
        
        # Apply filters
        filtered_data = position_data
        if urgency_filter != "ALL":
            filtered_data = [
                d for d in filtered_data
                if d["action_decision"] and d["action_decision"].urgency == urgency_filter
            ]
        
        if action_filter != "ALL":
            filtered_data = [
                d for d in filtered_data
                if d["action_decision"] and d["action_decision"].action == action_filter
            ]
        
        # Display filtered positions
        if not filtered_data:
            st.info(f"No positions match the selected filters (Urgency: {urgency_filter}, Action: {action_filter})")
        else:
            for i, data in enumerate(filtered_data):
                position = data["position"]
                action_decision = data["action_decision"]
                market_context = data["market_context"]
                
                # Get action and urgency (with fallbacks)
                if action_decision:
                    action = action_decision.action
                    urgency = action_decision.urgency
                    reason_codes = action_decision.reason_codes
                    explanation = action_decision.explanation
                    allowed_next_states = action_decision.allowed_next_states
                else:
                    action = "HOLD"
                    urgency = "LOW"
                    reason_codes = ["Action Engine evaluation unavailable"]
                    explanation = "Unable to evaluate position"
                    allowed_next_states = []
                
                # Calculate premium percentage
                premium_pct = 0.0
                if position.strike and position.strike > 0 and position.contracts > 0:
                    premium_per_contract = position.premium_collected / position.contracts
                    premium_pct = (premium_per_contract / (position.strike * 100)) * 100
                
                # Show position state
                position_state_str = position.state or (position.status if hasattr(position, 'status') else "OPEN")
                try:
                    position_state = PositionState(position_state_str)
                except (ValueError, AttributeError, TypeError):
                    position_state = PositionState.OPEN
                
                with st.container():
                    # Main row with columns
                    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1.2, 0.8, 1, 1, 0.8, 1, 1, 1, 1])
                    
                    with col1:
                        st.write(f"**{position.symbol}**")
                    
                    with col2:
                        st.caption(position.position_type)
                    
                    with col3:
                        st.caption(f"${position.strike:.2f}" if position.strike else "N/A")
                    
                    with col4:
                        st.caption(position.expiry or "N/A")
                    
                    with col5:
                        st.caption(f"{position.contracts}")
                    
                    with col6:
                        # State badge
                        if position_state in [PositionState.HOLD, PositionState.OPEN]:
                            state_color = "🟢"
                            state_style = "background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state in [PositionState.ROLL_CANDIDATE, PositionState.ROLLING]:
                            state_color = "🟡"
                            state_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state == PositionState.CLOSED:
                            state_color = "⚫"
                            state_style = "background-color: #e2e3e5; color: #383d41; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state == PositionState.ASSIGNED:
                            state_color = "🟣"
                            state_style = "background-color: #d1ecf1; color: #0c5460; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:
                            state_color = "⚪"
                            state_style = "background-color: #f8f9fa; color: #6c757d; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{state_style}">{state_color} {position_state.value}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col7:
                        # Action badge
                        if action == "HOLD":
                            action_color = "⚪"
                            action_style = "background-color: #e9ecef; color: #495057; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif action == "CLOSE":
                            action_color = "🔵"
                            action_style = "background-color: #cfe2ff; color: #084298; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif action == "ROLL":
                            action_color = "🟡"
                            action_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:  # ALERT
                            action_color = "🔴"
                            action_style = "background-color: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{action_style}">{action_color} {action}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col8:
                        # Urgency badge
                        if urgency == "HIGH":
                            urgency_color = "🔴"
                            urgency_style = "background-color: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif urgency == "MEDIUM":
                            urgency_color = "🟡"
                            urgency_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:  # LOW
                            urgency_color = "🟢"
                            urgency_style = "background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{urgency_style}">{urgency_color} {urgency}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col9:
                        st.caption(f"{premium_pct:.1f}%")
                    
                    # Expander for details including Action Engine information
                    with st.expander("📋 Details", expanded=False):
                        # Action Decision Section (Week 4 Day 2 Action Engine)
                        if action_decision:
                            st.write("**Action Decision:**")
                            col_a1, col_a2 = st.columns(2)
                            with col_a1:
                                st.metric("Action", action)
                            with col_a2:
                                st.metric("Urgency", urgency)
                            
                            # Explanation
                            if explanation:
                                st.write("**Explanation:**")
                                st.info(explanation)
                            
                            # Reason Codes
                            if reason_codes:
                                st.write("**Reason Codes:**")
                                for code in reason_codes:
                                    st.caption(f"• {code}")
                            
                            # Allowed Next States
                            if allowed_next_states:
                                st.write("**Allowed Next States:**")
                                states_str = ", ".join(allowed_next_states)
                                st.caption(states_str)
                            
                            st.divider()
                        
                        # Current State
                        st.write("**Current State:**")
                        st.write(f"`{position_state.value}`")
                        
                        # Allowed next states
                        allowed_next = get_allowed_transitions(position_state)
                        if allowed_next:
                            st.write("**Allowed Next States:**")
                            allowed_str = ", ".join([s.value for s in allowed_next])
                            st.caption(allowed_str)
                        else:
                            st.write("**Allowed Next States:**")
                            st.caption("None (terminal state)")
                        
                        # State History
                        st.write("**State History:**")
                        state_history = position.state_history or []
                        if state_history:
                            history_data = []
                            for event in state_history:
                                if isinstance(event, dict):
                                    history_data.append({
                                        "From": event.get("from_state", "N/A"),
                                        "To": event.get("to_state", "N/A"),
                                        "Reason": event.get("reason", "N/A"),
                                        "Source": event.get("source", "N/A"),
                                        "Timestamp": event.get("timestamp_iso", "N/A")[:19] if event.get("timestamp_iso") else "N/A",
                                    })
                                else:
                                    # Handle StateTransitionEvent objects
                                    history_data.append({
                                        "From": getattr(event, "from_state", "N/A"),
                                        "To": getattr(event, "to_state", "N/A"),
                                        "Reason": getattr(event, "reason", "N/A"),
                                        "Source": getattr(event, "source", "N/A"),
                                        "Timestamp": getattr(event, "timestamp_iso", "N/A")[:19] if hasattr(event, "timestamp_iso") else "N/A",
                                    })
                            
                            if history_data:
                                st.dataframe(pd.DataFrame(history_data), use_container_width=True, hide_index=True)
                            else:
                                st.caption("No state transitions recorded")
                        else:
                            st.caption("No state history available")
                
                if i < len(filtered_data) - 1:
                    st.divider()
    else:
        st.info("No open positions.")

    st.divider()

    # Alerts Section (Phase 1A.1 - with grouping, scroll, bulk actions)
    st.header("🔔 Alerts")
    
    # Alert status filter
    alert_status_filter = st.selectbox(
        "Filter by Status",
        ["OPEN", "ACKED", "ARCHIVED", "ALL"],
        index=0,
        key="alert_status_filter"
    )
    
    status_filter = None if alert_status_filter == "ALL" else alert_status_filter
    all_alerts = get_alerts(limit=200, status=status_filter)
    
    # Filter out system/internal errors (only show operator alerts)
    operator_alerts = [
        a for a in all_alerts
        if a.get("level", "").upper() in ["INFO", "WATCH", "ACTION", "HALT"]
    ]
    
    if operator_alerts:
        # Bulk actions
        col_bulk1, col_bulk2 = st.columns(2)
        with col_bulk1:
            if st.button("✓ Ack All (Visible)", use_container_width=True, key="bulk_ack"):
                visible_ids = [a["id"] for a in operator_alerts if a.get("status") == "OPEN"]
                if visible_ids:
                    bulk_ack_alerts(visible_ids)
                    st.success(f"✅ Acknowledged {len(visible_ids)} alert(s)")
                    st.rerun()
        with col_bulk2:
            if st.button("📦 Archive All (Non-Action)", use_container_width=True, key="bulk_archive"):
                non_action_ids = [a["id"] for a in operator_alerts if a.get("level") != "ACTION" and a.get("status") != "ARCHIVED"]
                if non_action_ids:
                    bulk_archive_non_action_alerts(non_action_ids)
                    st.success(f"✅ Archived {len(non_action_ids)} alert(s)")
                    st.rerun()
        
        # Group alerts by date
        from datetime import date as date_type
        today = date_type.today()
        yesterday = date_type.fromordinal(today.toordinal() - 1)
        
        alerts_today = []
        alerts_yesterday = []
        alerts_older = []
        
        for alert in operator_alerts:
            try:
                alert_date_str = alert.get("created_at", "")[:10]  # YYYY-MM-DD
                if alert_date_str:
                    alert_date = date_type.fromisoformat(alert_date_str)
                    if alert_date == today:
                        alerts_today.append(alert)
                    elif alert_date == yesterday:
                        alerts_yesterday.append(alert)
                    else:
                        alerts_older.append(alert)
                else:
                    alerts_older.append(alert)
            except Exception:
                alerts_older.append(alert)
        
        # Scrollable container with fixed max height
        alerts_container = st.container()
        with alerts_container:
            # Use custom CSS for scroll containment
            st.markdown("""
                <style>
                .alerts-scroll-container {
                    max-height: 400px;
                    overflow-y: auto;
                    border: 1px solid #e0e0e0;
                    border-radius: 5px;
                    padding: 10px;
                }
                </style>
            """, unsafe_allow_html=True)
            
            alerts_html = '<div class="alerts-scroll-container">'
            
            # Today (expanded by default)
            if alerts_today:
                with st.expander(f"📅 Today ({len(alerts_today)})", expanded=True):
                    for alert in alerts_today:
                        _render_alert(alert)
            
            # Yesterday (collapsed by default)
            if alerts_yesterday:
                with st.expander(f"📅 Yesterday ({len(alerts_yesterday)})", expanded=False):
                    for alert in alerts_yesterday:
                        _render_alert(alert)
            
            # Older (collapsed by default)
            if alerts_older:
                with st.expander(f"📅 Older ({len(alerts_older)})", expanded=False):
                    for alert in alerts_older:
                        _render_alert(alert)
    else:
        st.info("✅ No alerts found.")
    
    st.divider()

    # Backtest Section (Phase 5 – DEV only)
    st.header("📉 Backtest", anchor="backtest")
    _dev_mode_bt = os.environ.get("CHAKRAOPS_DEV", "").lower() in ("1", "true", "yes")
    if _dev_mode_bt:
        try:
            from app.core.config.paths import BASE_DIR
            _backtest_base = BASE_DIR / "app" / "data" / "backtests"
        except Exception:
            _backtest_base = Path(__file__).resolve().parents[2] / "data" / "backtests"
        if st.button("Run backtest (fixtures)", key="backtest_run", use_container_width=True):
            try:
                from app.backtest.engine import BacktestEngine, BacktestConfig, SnapshotCSVDataSource
                _fixtures = _backtest_base.parent / "backtest_fixtures" / "snapshots"
                if not _fixtures.exists():
                    st.warning("No fixture folder found. Create dated snapshot CSVs in `app/data/backtest_fixtures/snapshots/` (e.g. 2026-01-01.csv) or run the fixture generator.")
                else:
                    _ds = SnapshotCSVDataSource(_fixtures)
                    _cfg = BacktestConfig(data_source=_ds, output_dir=_backtest_base)
                    _eng = BacktestEngine(_cfg)
                    with st.spinner("Running backtest..."):
                        _report = _eng.run(_cfg)
                    st.session_state["backtest_last_run_id"] = _report.run_id
                    st.success(f"Backtest complete: run_id={_report.run_id} | PnL={_report.total_pnl:.2f} | trades={_report.total_trades}")
                    st.rerun()
            except Exception as e:
                st.error(f"Backtest failed: {e}")
                import traceback
                st.code(traceback.format_exc())
        # Last report summary: prefer session last_run_id, else newest by mtime
        _last_id = st.session_state.get("backtest_last_run_id")
        _report_path = None
        if _backtest_base.exists():
            if _last_id:
                _rp = _backtest_base / _last_id / "backtest_report.json"
                if _rp.exists():
                    _report_path = _rp
            if _report_path is None:
                _candidates = [_d / "backtest_report.json" for _d in _backtest_base.iterdir() if _d.is_dir() and (_d / "backtest_report.json").exists()]
                if _candidates:
                    _report_path = max(_candidates, key=lambda p: p.stat().st_mtime)
        if _report_path and _report_path.exists():
            with open(_report_path, "r", encoding="utf-8") as f:
                _report_json = json.load(f)
            st.subheader("Last report summary")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total PnL", f"{_report_json.get('total_pnl', 0):.2f}")
            with c2:
                st.metric("Win rate", f"{_report_json.get('win_rate', 0)*100:.1f}%")
            with c3:
                st.metric("Trades", _report_json.get("total_trades", 0))
            with c4:
                st.metric("Max DD", f"{_report_json.get('max_drawdown', 0):.2f}")
            _trades_path = _report_path.parent / "backtest_trades.csv"
            if _trades_path.exists():
                import pandas as pd
                _df = pd.read_csv(_trades_path)
                st.dataframe(_df, use_container_width=True, height=min(400, 80 + 35 * len(_df)))
        else:
            st.caption("No backtest report yet. Run backtest (requires fixture folder).")
    else:
        st.caption("Backtest is available in DEV mode (CHAKRAOPS_DEV=1).")
    
    st.divider()
    
    # Symbol Universe Manager Section (Phase 2B Step 4)
    st.header("Symbol Universe Manager", anchor="symbol-universe-manager")

    try:
        symbols = get_all_symbols()

        # Add Symbol (no modals - Streamlit compatibility)
        with st.expander("➕ Add Symbol", expanded=False):
            new_symbol = st.text_input("Symbol", key="universe_add_symbol", placeholder="AAPL")
            new_notes = st.text_area("Notes", key="universe_add_notes", placeholder="Optional notes")
            if st.button("Save Symbol", key="universe_add_save", use_container_width=True):
                if not new_symbol.strip():
                    st.warning("Please enter a symbol")
                else:
                    try:
                        add_symbol(new_symbol, new_notes)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        # Table header
        if symbols:
            if "universe_delete_confirm" not in st.session_state:
                st.session_state.universe_delete_confirm = None

            col_sym_h, col_enabled_h, col_notes_h, col_actions_h = st.columns([2, 1, 4, 2])
            with col_sym_h:
                st.write("**Symbol**")
            with col_enabled_h:
                st.write("**Enabled**")
            with col_notes_h:
                st.write("**Notes**")
            with col_actions_h:
                st.write("**Actions**")
            st.divider()

            # Rows
            for i, symbol_data in enumerate(symbols):
                symbol = symbol_data["symbol"]
                enabled = bool(symbol_data["enabled"])
                notes = symbol_data.get("notes", "") or ""

                col_sym, col_enabled, col_notes, col_actions = st.columns([2, 1, 4, 2])
                with col_sym:
                    st.write(symbol)

                with col_enabled:
                    new_enabled = st.toggle(
                        "Enabled",
                        value=enabled,
                        key=f"toggle_{symbol}",
                        label_visibility="collapsed",
                    )
                    if new_enabled != enabled:
                        toggle_symbol(symbol, new_enabled)
                        st.rerun()

                with col_notes:
                    st.caption(notes if notes else "(no notes)")

                with col_actions:
                    # Delete is button + inline confirmation (no modals)
                    if st.button("Delete", key=f"delete_{symbol}", use_container_width=True):
                        st.session_state.universe_delete_confirm = symbol
                        st.rerun()

                # Inline edit expander per row (no modals)
                with st.expander(f"Edit {symbol}", expanded=False):
                    edit_enabled = st.checkbox(
                        "Enabled",
                        value=enabled,
                        key=f"edit_enabled_{symbol}",
                    )
                    edit_notes = st.text_area(
                        "Notes",
                        value=notes,
                        key=f"edit_notes_{symbol}",
                    )
                    if st.button("Save Changes", key=f"edit_save_{symbol}", use_container_width=True):
                        try:
                            update_symbol(symbol, edit_enabled, edit_notes)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

                # Inline delete confirmation row
                if st.session_state.universe_delete_confirm == symbol:
                    st.warning(f"Confirm delete: {symbol}")
                    col_yes, col_no = st.columns([1, 1])
                    with col_yes:
                        if st.button("Yes, delete", key=f"delete_yes_{symbol}", use_container_width=True):
                            try:
                                delete_symbol(symbol)
                                st.session_state.universe_delete_confirm = None
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with col_no:
                        if st.button("Cancel", key=f"delete_no_{symbol}", use_container_width=True):
                            st.session_state.universe_delete_confirm = None
                            st.rerun()

                if i < len(symbols) - 1:
                    st.divider()
        else:
            st.info("No symbols in universe. Add symbols using the expander above.")
    except Exception as e:
        st.warning(f"Unable to load universe: {e}")


if __name__ == "__main__":
    main()
