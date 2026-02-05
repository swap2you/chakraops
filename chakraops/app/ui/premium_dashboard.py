# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Premium ChakraOps Dashboard — Option Alpha-style trading platform UI.

A modern, professional trading dashboard with:
- Fixed sidebar toggle always visible
- Collapsible sidebar (icons only when collapsed)
- Test page for single-ticker data fetching and Slack simulation
- Horizontal charts with color coding
- Improved metrics with icons and clear scoring
- Streamlined header and responsive layout
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Load .env so ORATS_API_TOKEN is available when run via Streamlit
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# Try to import Slack notifier for Test page
try:
    from app.notifications.slack_notifier import slack_webhook_available
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    def slack_webhook_available() -> Tuple[bool, str]:
        return False, "Slack notifier not available"

# Try to import ORATS options provider for Test page
try:
    from app.data.options_chain_provider import OratsOptionsChainProvider
    ORATS_AVAILABLE = True
except ImportError:
    ORATS_AVAILABLE = False
    OratsOptionsChainProvider = None  # type: ignore

DATA_SOURCE_LIVE = "live"
DATA_SOURCE_SNAPSHOT = "snapshot"

import streamlit as st

from app.ui.safe_ui import ensure_dict, ensure_list

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUT_DIR = Path("out")
DECISION_LATEST = OUT_DIR / "decision_latest.json"
SAMPLE_DECISION_RICH = OUT_DIR / "sample_decision_rich.json"
SAMPLE_DECISION = OUT_DIR / "sample_decision.json"

# Sidebar widths
SIDEBAR_EXPANDED_WIDTH = 220
SIDEBAR_COLLAPSED_WIDTH = 70

# Scoring configuration
SCORE_MAX = 5.0  # Maximum possible score

# Common test symbols
TEST_SYMBOLS = ["AAPL", "NVDA", "NFLX", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "AMD", "CRM"]

# ---------------------------------------------------------------------------
# Safe Formatting Helpers
# ---------------------------------------------------------------------------

def safe_format(value: Any, fmt: str = ".2f", default: str = "N/A") -> str:
    """Format a numeric value safely, returning default if None or invalid."""
    if value is None:
        return default
    try:
        if isinstance(value, (int, float)):
            return format(value, fmt)
        return str(value)
    except (TypeError, ValueError):
        return default


def safe_percent(value: Any, default: str = "N/A") -> str:
    """Format a value as percentage (e.g., 0.15 -> '15%')."""
    if value is None:
        return default
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return default


def safe_currency(value: Any, default: str = "N/A") -> str:
    """Format a value as currency (e.g., 1.50 -> '$1.50')."""
    if value is None:
        return default
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return default


def format_with_waiver(value: Any, waiver_reason: Optional[str], field_name: str, default: str = "N/A") -> str:
    """
    Format a value, showing WAIVED if value is None but waiver_reason is set.
    
    Args:
        value: The value to format
        waiver_reason: e.g. "DERIVED_FROM_OPRA" 
        field_name: Name of the field (for tooltip)
        default: Default to show if not waived
    
    Returns:
        Formatted string or "WAIVED" with appropriate styling
    """
    if value is not None:
        return str(value)
    if waiver_reason:
        # Show WAIVED with tooltip hint
        return f'<span class="waived-field" title="Underlying {field_name} waived - options liquidity confirmed ({waiver_reason})">WAIVED</span>'
    return default


def format_stock_field(value: Any, waiver_reason: Optional[str], field_name: str, 
                       is_currency: bool = False, is_volume: bool = False) -> str:
    """
    Format stock snapshot field with waiver support.
    
    Args:
        value: The value to format
        waiver_reason: e.g. "DERIVED_FROM_OPRA"
        field_name: Name of the field (bid, ask, volume, avg_volume)
        is_currency: Format as currency
        is_volume: Format as volume (K/M)
    """
    if value is not None:
        if is_currency:
            return f"${float(value):.2f}"
        if is_volume:
            v = float(value)
            if v >= 1_000_000:
                return f"{v/1_000_000:.1f}M"
            if v >= 1_000:
                return f"{v/1_000:.1f}K"
            return f"{v:.0f}"
        return str(value)
    
    # Value is None - check if waived
    if waiver_reason:
        tooltip = f"Underlying {field_name} not required - options liquidity confirmed ({waiver_reason})"
        return f'<span style="color:#6b7280;font-style:italic;" title="{tooltip}">WAIVED</span>'
    
    return "N/A"


def get_eligibility_label(position_open: bool, position_reason: Optional[str] = None) -> str:
    """
    Get eligibility label based on position status.
    
    Args:
        position_open: Whether a position is already open for this symbol
        position_reason: Optional reason string
    
    Returns:
        Eligibility label string (e.g., "Eligible for: CSP (Wheel entry)")
    """
    if position_open:
        return "Eligible for: CC (Wheel continuation)"
    else:
        return "Eligible for: CSP (Wheel entry)"


def get_eligibility_badge_html(position_open: bool, position_reason: Optional[str] = None) -> str:
    """
    Get HTML badge for eligibility type.
    
    Args:
        position_open: Whether a position is already open for this symbol
        position_reason: Optional reason string
    
    Returns:
        HTML badge string
    """
    if position_open:
        return '<span style="background:#7c3aed;color:#fff;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.7rem;font-weight:600;">CC</span>'
    else:
        return '<span style="background:#0284c7;color:#fff;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.7rem;font-weight:600;">CSP</span>'


def format_gate_status(status: str) -> str:
    """Format gate status as styled HTML badge."""
    if status == "PASS":
        return '<span class="gate-pass">PASS</span>'
    elif status == "FAIL":
        return '<span class="gate-fail">FAIL</span>'
    elif status == "WAIVED":
        return '<span class="gate-waived">WAIVED</span>'
    return f'<span style="padding:0.15rem 0.4rem;font-size:0.7rem;">{status}</span>'


def format_selected_contract_html(selected_contract: Optional[Dict[str, Any]]) -> str:
    """
    Format selected contract as HTML for display next to Greeks summary.
    
    Args:
        selected_contract: Dict with expiry, strike, option_type, occ_symbol, delta, dte
    
    Returns:
        HTML string showing the selected contract
    """
    if not selected_contract:
        return '<span style="color:#6b7280;font-style:italic;">No contract selected</span>'
    
    expiry = selected_contract.get("expiry", "—")
    strike = selected_contract.get("strike")
    option_type = selected_contract.get("option_type", "—")
    delta = selected_contract.get("delta")
    dte = selected_contract.get("dte")
    occ_symbol = selected_contract.get("occ_symbol", "")
    
    strike_str = f"${strike:.2f}" if strike else "—"
    delta_str = f"{delta:.2f}" if delta else "—"
    dte_str = f"{dte}d" if dte else "—"
    
    return f'''<div class="selected-contract">
        <strong>Selected Contract:</strong> {occ_symbol or f"{option_type} {strike_str}"}<br>
        <span style="font-size:0.75rem;color:var(--text-muted);">
            Exp: {expiry} | Strike: {strike_str} | Delta: {delta_str} | DTE: {dte_str}
        </span>
    </div>'''


def compute_csp_notional(strike: Optional[float]) -> Optional[float]:
    """
    Compute CSP notional (capital required) = strike × 100.
    
    Args:
        strike: Option strike price
    
    Returns:
        Notional value or None if strike is None
    """
    if strike is None:
        return None
    return float(strike) * 100


def safe_delta(value: Any, default: str = "N/A") -> str:
    """Format delta value (e.g., -0.25 -> '-0.25')."""
    if value is None:
        return default
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return default


NAV_ITEMS = [
    ("Dashboard", "dashboard", "📊"),
    ("Positions", "positions", "📋"),
    ("Test", "test", "🧪"),
    ("Strategies", "strategies", "🎯"),
    ("Analytics", "analytics", "📈"),
    ("History", "history", "📜"),
    ("Settings", "settings", "⚙️"),
]

# Metric icons and configuration
METRIC_CONFIG = {
    "Total Symbols": {"icon": "🌐", "tooltip": "Total symbols in universe"},
    "Evaluated": {"icon": "🔍", "tooltip": "Symbols evaluated for options"},
    "Candidates": {"icon": "📋", "tooltip": "Positions passing all filters"},
    "Selected": {"icon": "✅", "tooltip": "Chosen for execution"},
    "Missing Chains": {"icon": "⚠️", "tooltip": "No options data available"},
    "Exclusions": {"icon": "🚫", "tooltip": "Filter rejections"},
}

# Color palette - refined
COLORS = {
    "primary": "#0066b8",
    "primary_dark": "#004d8c",
    "success": "#2aa872",
    "success_border": "#1e8a5e",
    "warning": "#d4940a",
    "warning_border": "#b37d08",
    "danger": "#d9534f",
    "danger_border": "#c9302c",
    "neutral": "#6c757d",
    "purple": "#7c3aed",
    "surface_light": "#ffffff",
    "surface_dark": "#1a1f2e",
    "bg_light": "#f5f7fa",
    "bg_dark": "#0d1117",
    "text_light": "#24292f",
    "text_dark": "#e6edf3",
    "border_light": "#d0d7de",
    "border_dark": "#30363d",
}

# Exclusion rule colors
EXCLUSION_COLORS = {
    "SPREAD_TOO_WIDE": "#dc2626",
    "NO_EXPIRATIONS": "#f59e0b",
    "DELTA_OUT_OF_RANGE": "#8b5cf6",
    "LOW_OPEN_INTEREST": "#3b82f6",
    "BID_BELOW_MIN": "#ef4444",
    "NO_OPTIONS_FOR_SYMBOL": "#6b7280",
}

# Strategy colors
STRATEGY_COLORS = {
    "CSP": "#0066b8",
    "CC": "#7c3aed",
    "PUT": "#dc2626",
    "CALL": "#16a34a",
    "Other": "#6b7280",
}

# Card tooltips
CARD_TOOLTIPS = {
    "Exclusion Breakdown": "Symbols rejected by each filter rule",
    "Candidate Distribution": "Candidates by strategy (CSP/CC/PUT/CALL)",
    "Top Candidates": "Highest-scoring positions after filters",
    "Selected Signals": "Signals for execution with Slack alerts",
    "Exclusions by Rule": "Details of rejected symbols",
    "Execution Plan": "Orders ready for execution",
}


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------


def get_available_snapshots() -> List[str]:
    """Get list of available snapshot files."""
    if not OUT_DIR.exists():
        return []
    
    files = []
    if DECISION_LATEST.exists():
        files.append(DECISION_LATEST.name)
    if SAMPLE_DECISION_RICH.exists():
        files.append(SAMPLE_DECISION_RICH.name)
    if SAMPLE_DECISION.exists():
        files.append(SAMPLE_DECISION.name)
    
    for f in sorted(OUT_DIR.glob("decision_*.json"), reverse=True):
        if f.name not in files:
            files.append(f.name)
    
    return files[:20]


def load_decision_data(filename: Optional[str] = None) -> Tuple[Dict[str, Any], bool, str, Optional[str]]:
    """Load decision data from specified file or auto-detect."""
    error_msg = None
    
    if filename and filename != "No files available":
        filepath = OUT_DIR / filename
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                is_sample = "sample" in filename.lower()
                return data, is_sample, filename, None
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON: {e}"
            except IOError as e:
                error_msg = f"Read error: {e}"
        else:
            error_msg = f"File not found: {filename}"
    
    # Auto-detect
    for path, is_sample_flag in [(DECISION_LATEST, False), (SAMPLE_DECISION_RICH, True), (SAMPLE_DECISION, True)]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data, is_sample_flag, path.name, error_msg
            except (json.JSONDecodeError, IOError):
                continue
    
    return {
        "decision_snapshot": {"stats": {}, "candidates": [], "selected_signals": [], "exclusions": []},
        "execution_gate": {"allowed": False},
        "execution_plan": {"orders": []},
    }, True, "none", error_msg or "No data files found"


def parse_snapshot(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse decision snapshot into component parts. Safe when data is None or missing keys."""
    data = data or {}
    snapshot = data.get("decision_snapshot") or {}
    return {
        "stats": snapshot.get("stats") or {},
        "candidates": snapshot.get("candidates") or [],
        "scored_candidates": snapshot.get("scored_candidates") or [],
        "selected_signals": snapshot.get("selected_signals") or [],
        "exclusions": snapshot.get("exclusions") or [],
        "exclusion_summary": snapshot.get("exclusion_summary") or {},
        "symbols_with_options": snapshot.get("symbols_with_options") or [],
        "symbols_without_options": snapshot.get("symbols_without_options") or {},
        "data_source": snapshot.get("data_source") or "unknown",
        "as_of": snapshot.get("as_of") or "",
    }


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _extract_score(score_val: Any) -> float:
    if score_val is None:
        return 0.0
    if isinstance(score_val, dict):
        return _safe_float(score_val.get("total", 0))
    return _safe_float(score_val)


def _format_score(score: float) -> str:
    """Format score with value and percentage."""
    pct = min(100, (score / SCORE_MAX) * 100)
    return f"{score:.2f} ({pct:.0f}%)"


def _get_strategy_label(candidate: Dict[str, Any]) -> str:
    signal_type = candidate.get("signal_type", "")
    if signal_type and signal_type not in ("", "Unknown"):
        return signal_type
    strategy = candidate.get("strategy", "")
    if strategy and strategy not in ("", "Unknown"):
        return strategy
    option_type = candidate.get("option_type", "")
    if option_type:
        return "PUT" if option_type.upper() in ("PUT", "P") else "CALL"
    return "Other"


def _humanize_label(key: str) -> str:
    if not key:
        return key
    return " ".join(w.capitalize() for w in str(key).replace("_", " ").split())


def _generate_slack_message(candidate: Dict[str, Any]) -> str:
    symbol = candidate.get("symbol", "???")
    strike = _safe_float(candidate.get("strike", 0))
    expiry = candidate.get("expiry", "") or candidate.get("expiration", "N/A")
    mid = _safe_float(candidate.get("mid", 0))
    signal_type = _get_strategy_label(candidate)
    option_char = "P" if signal_type in ("CSP", "PUT") else "C"
    return f"📊 *SELL 1 {symbol} ${strike:.0f}{option_char}* exp {expiry} @ *${mid:.2f}* credit"


def _tooltip(text: str) -> str:
    """Generate tooltip HTML using abbr tag."""
    escaped = text.replace('"', '&quot;')
    return f'<abbr title="{escaped}" style="cursor:help;text-decoration:none;border:none;"><span style="display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;background:rgba(0,102,184,0.12);color:#0066b8;font-size:0.6rem;font-weight:600;margin-left:3px;">?</span></abbr>'


# ---------------------------------------------------------------------------
# CSS Injection
# ---------------------------------------------------------------------------


def inject_premium_css(dark: bool = False, sidebar_collapsed: bool = False) -> None:
    """Inject premium dashboard CSS."""
    bg = COLORS["bg_dark"] if dark else COLORS["bg_light"]
    surface = COLORS["surface_dark"] if dark else COLORS["surface_light"]
    text = COLORS["text_dark"] if dark else COLORS["text_light"]
    text_muted = "#8b949e" if dark else "#57606a"
    border = COLORS["border_dark"] if dark else COLORS["border_light"]
    sidebar_width = SIDEBAR_COLLAPSED_WIDTH if sidebar_collapsed else SIDEBAR_EXPANDED_WIDTH
    
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap');
    
    :root {{
        --bg: {bg}; --surface: {surface}; --border: {border};
        --text: {text}; --text-muted: {text_muted};
        --primary: {COLORS['primary']}; --success: {COLORS['success']};
        --warning: {COLORS['warning']}; --danger: {COLORS['danger']};
    }}
    
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
    .stApp {{ background: var(--bg); }}
    .main .block-container {{ max-width: 1400px; padding: 0.25rem 1.5rem 1.5rem; }}
    #MainMenu, footer, header[data-testid="stHeader"] {{ display: none; }}
    
    /* Sidebar toggle - ALWAYS visible */
    [data-testid="collapsedControl"] {{
        position: fixed !important;
        left: 8px !important;
        top: 12px !important;
        z-index: 999999 !important;
        background: {'#1e293b' if dark else '#fff'} !important;
        border: 2px solid {'#3b82f6' if dark else '#0066b8'} !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        width: 32px !important; height: 32px !important;
        display: flex !important; align-items: center !important; justify-content: center !important;
    }}
    [data-testid="collapsedControl"] svg {{ color: {'#60a5fa' if dark else '#0066b8'} !important; }}
    
    /* Sidebar */
    [data-testid="stSidebar"] {{
        width: {sidebar_width}px !important;
        min-width: {sidebar_width}px !important;
        background: {'#0f172a' if dark else '#1e293b'} !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top: 3rem; width: {sidebar_width}px !important; }}
    
    /* Nav buttons - compact */
    [data-testid="stSidebar"] .stButton > button {{
        background: transparent !important;
        color: #94a3b8 !important;
        border: none !important;
        text-align: {'center' if sidebar_collapsed else 'left'} !important;
        padding: 0.4rem {'0.5rem' if sidebar_collapsed else '0.6rem'} !important;
        font-size: {'1.1rem' if sidebar_collapsed else '0.8rem'} !important;
        min-height: 36px !important;
        transition: all 0.15s !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(255,255,255,0.1) !important;
        color: #fff !important;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background: rgba(0,102,184,0.25) !important;
        color: #60a5fa !important;
        border-left: {'none' if sidebar_collapsed else '3px solid #3b82f6'} !important;
    }}
    
    /* Header bar - compact */
    .header-bar {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_dark']} 100%);
        padding: 0.5rem 1rem;
        margin: -0.25rem -1.5rem 1rem;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    }}
    .header-brand {{ display: flex; align-items: center; gap: 0.5rem; }}
    .header-logo {{ width: 32px; height: 32px; background: rgba(255,255,255,0.15); border-radius: 8px;
        display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }}
    .header-title {{ color: #fff; font-size: 1.1rem; font-weight: 700; margin: 0; }}
    .header-subtitle {{ color: rgba(255,255,255,0.7); font-size: 0.6rem; margin: 0; text-transform: uppercase; }}
    .header-badge {{ background: rgba(255,255,255,0.15); color: #fff; padding: 0.25rem 0.5rem;
        border-radius: 4px; font-size: 0.65rem; font-weight: 600; }}
    
    /* Cards */
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
        padding: 1rem; margin-bottom: 0.75rem; box-shadow: 0 1px 4px rgba(0,0,0,0.03); }}
    .card-title {{ font-size: 0.85rem; font-weight: 600; color: var(--text); margin: 0 0 0.75rem 0;
        display: flex; align-items: center; gap: 0.4rem; }}
    
    /* Metric tiles - icon on top, value below */
    .metric-tile {{
        background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
        padding: 0.6rem 0.5rem; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        transition: transform 0.15s, box-shadow 0.15s;
    }}
    .metric-tile:hover {{ transform: translateY(-1px); box-shadow: 0 3px 8px rgba(0,0,0,0.06); }}
    .metric-tile.success {{ border-left: 4px solid {COLORS['success_border']}; }}
    .metric-tile.warning {{ border-left: 4px solid {COLORS['warning_border']}; }}
    .metric-tile.danger {{ border-left: 4px solid {COLORS['danger_border']}; }}
    .metric-icon {{ font-size: 1.3rem; margin-bottom: 0.2rem; }}
    .metric-value {{ font-size: 1.4rem; font-weight: 700; color: var(--text); line-height: 1.2; }}
    .metric-value.success {{ color: {COLORS['success']}; }}
    .metric-value.warning {{ color: {COLORS['warning']}; }}
    .metric-value.danger {{ color: {COLORS['danger']}; }}
    .metric-label {{ font-size: 0.55rem; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: 0.04em; margin-top: 0.2rem; }}
    
    /* Hero section */
    .hero {{ background: linear-gradient(135deg, var(--surface) 0%, {'#1a1f2e' if dark else '#f0f4f8'} 100%);
        border: 1px solid var(--border); border-radius: 12px; padding: 0.75rem 1rem; margin-bottom: 1rem; }}
    .status-badge {{ display: inline-flex; padding: 0.3rem 0.6rem; border-radius: 6px;
        font-weight: 600; font-size: 0.7rem; margin-right: 0.5rem; }}
    .status-allowed {{ background: #dcfce7; color: #166534; }}
    .status-blocked {{ background: #fee2e2; color: #991b1b; }}
    .status-live {{ background: #dbeafe; color: #1e40af; }}
    .status-sample {{ background: #f3f4f6; color: #374151; }}
    
    /* Slack message */
    .slack-msg {{
        background: {'#2d333b' if dark else '#f1f5f9'};
        border-left: 4px solid {COLORS['primary']};
        padding: 0.6rem 0.8rem; margin-top: 0.4rem; border-radius: 0 6px 6px 0;
        font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
        color: var(--text); line-height: 1.4;
    }}
    
    /* Strategy badges */
    .strat-badge {{ display: inline-block; padding: 0.15rem 0.4rem; border-radius: 4px;
        font-size: 0.6rem; font-weight: 600; }}
    .strat-csp {{ background: #dbeafe; color: #1e40af; }}
    .strat-cc {{ background: #f3e8ff; color: #7c3aed; }}
    .strat-put {{ background: #fee2e2; color: #991b1b; }}
    .strat-call {{ background: #dcfce7; color: #166534; }}
    
    /* Tables */
    div[data-testid="stDataFrameResizable"] {{ border: 1px solid var(--border); border-radius: 8px; }}
    
    /* Test page */
    .test-result {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
        padding: 1rem; margin-top: 0.75rem; }}
    
    /* Footer */
    .footer {{ margin-top: 1.5rem; padding: 0.5rem; text-align: center;
        color: var(--text-muted); font-size: 0.65rem; }}
    .footer a {{ color: {COLORS['primary']}; text-decoration: none; }}
    
    /* Waived field styling - for data waived due to options liquidity confirmation */
    .waived-field {{
        color: var(--text-muted);
        font-style: italic;
        font-size: 0.85em;
        padding: 0.1rem 0.3rem;
        background: rgba(107, 114, 128, 0.1);
        border-radius: 3px;
        cursor: help;
    }}
    
    /* Gate status badges */
    .gate-pass {{ background: #dcfce7; color: #166534; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.7rem; }}
    .gate-fail {{ background: #fee2e2; color: #991b1b; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.7rem; }}
    .gate-waived {{ background: #fef3c7; color: #92400e; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.7rem; }}
    
    /* Selected contract display */
    .selected-contract {{
        background: rgba(59, 130, 246, 0.1);
        border-left: 3px solid #3b82f6;
        padding: 0.5rem 0.75rem;
        margin: 0.5rem 0;
        border-radius: 0 4px 4px 0;
        font-size: 0.8rem;
    }}
    
    /* Responsive */
    @media (max-width: 1366px) {{
        .main .block-container {{ padding: 0.25rem 1rem 1rem; }}
        .metric-value {{ font-size: 1.2rem; }}
    }}
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Component Renderers
# ---------------------------------------------------------------------------


def render_header(is_sample: bool, loaded_file: str, available_files: List[str], data_source: str = "unknown") -> Tuple[bool, Optional[str], bool]:
    """Render compact header bar. Returns (new_dark, new_file, refresh_clicked)."""
    st.markdown("""
    <div class="header-bar">
        <div class="header-brand">
            <div class="header-logo">⚡</div>
            <div>
                <p class="header-title">ChakraOps</p>
                <p class="header-subtitle">Options Platform</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Controls row
    c1, c2, c3, c4, c5 = st.columns([2.5, 1, 0.8, 0.8, 0.8])
    
    with c1:
        idx = available_files.index(loaded_file) if loaded_file in available_files else 0
        selected = st.selectbox("📁", available_files or ["No files"], index=idx,
                                 key="file_sel", label_visibility="collapsed",
                                 help="Select data file")
    
    with c2:
        # Determine badge based on actual data_source
        if data_source == "live":
            badge_type = "🟢 Live"
            badge_color = "#2aa872"
        elif data_source == "snapshot":
            badge_type = "🟡 Snapshot"
            badge_color = "#d4940a"
        elif is_sample:
            badge_type = "⚪ Sample"
            badge_color = "#6b7280"
        else:
            badge_type = "📁 File"
            badge_color = "#6b7280"
        
        short_file = loaded_file[:18] + "..." if len(loaded_file) > 18 else loaded_file
        st.markdown(f'<div style="padding-top:0.5rem;"><span class="header-badge" style="background:{badge_color};">{badge_type}</span> <span style="font-size:0.65rem;color:var(--text-muted);">{short_file}</span></div>', unsafe_allow_html=True)
    
    with c3:
        dark = st.toggle("🌙", value=st.session_state.get("dark_mode", False), key="dark_toggle")
    
    with c4:
        refresh = st.button("🔄", key="refresh_btn", help="Refresh")
    
    file_changed = selected != loaded_file and selected != "No files"
    return dark, selected if file_changed else None, refresh


def render_sidebar(current_page: str, collapsed: bool) -> Tuple[str, bool]:
    """Render sidebar navigation."""
    with st.sidebar:
        if not collapsed:
            st.markdown('<div style="padding:0.25rem;margin-bottom:0.5rem;"><span style="color:#fff;font-size:0.9rem;font-weight:700;">⚡ ChakraOps</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="text-align:center;padding:0.25rem;margin-bottom:0.5rem;font-size:1.2rem;">⚡</div>', unsafe_allow_html=True)
        
        new_collapsed = st.checkbox("◀" if not collapsed else "▶", value=collapsed,
                                     key="collapse_chk", help="Collapse/expand")
        
        selected = current_page
        for label, page_id, icon in NAV_ITEMS:
            is_active = page_id == current_page
            btn_label = icon if collapsed else f"{icon} {label}"
            if st.button(btn_label, key=f"nav_{page_id}", use_container_width=True,
                        type="primary" if is_active else "secondary",
                        help=label if collapsed else None):
                selected = page_id
        
        if not collapsed:
            st.markdown("<hr style='border-color:rgba(255,255,255,0.1);margin:0.5rem 0;'>", unsafe_allow_html=True)
            st.markdown('<div style="font-size:0.6rem;color:#64748b;padding:0.3rem;">📡 Active</div>', unsafe_allow_html=True)
    
    return selected, new_collapsed


def _trust_first_hero_state(data: Optional[Dict], parsed: Optional[Dict]) -> Dict[str, Any]:
    """Phase 5.4: Compute trust-first hero headline and trust section data. Phase 6.1: run_mode, config_frozen."""
    data = ensure_dict(data)
    parsed = ensure_dict(parsed)
    daily = ensure_dict(data.get("daily_trust_report"))
    proposal = ensure_dict(parsed.get("trade_proposal"))
    why = ensure_dict(parsed.get("why_no_trade"))
    metadata = ensure_dict(data.get("metadata"))
    trades_ready = int(daily.get("trades_ready", 0))
    if trades_ready == 0 and proposal.get("execution_status") == "READY":
        trades_ready = 1
    headline = "NO TRADE — CAPITAL PROTECTED"
    if trades_ready >= 1:
        headline = "1 SAFE TRADE AVAILABLE" if trades_ready == 1 else f"{trades_ready} SAFE TRADES AVAILABLE"
    why_summary = why.get("summary") or daily.get("summary") or ""
    top_reasons = ensure_list(daily.get("top_blocking_reasons"))
    primary_reasons = ensure_list(why.get("primary_reasons"))
    if not top_reasons and primary_reasons:
        top_reasons = [{"code": ensure_dict(r).get("code", ""), "count": ensure_dict(r).get("count", 0)} for r in primary_reasons[:5]]
    risk_posture = (metadata.get("risk_posture") or "CONSERVATIVE").strip().upper()
    run_mode = (metadata.get("run_mode") or daily.get("run_mode") or "DRY_RUN").strip().upper()
    config_frozen = metadata.get("config_frozen") if "config_frozen" in metadata else daily.get("config_frozen")
    return {"headline": headline, "why_summary": why_summary, "top_reasons": top_reasons, "risk_posture": risk_posture, "run_mode": run_mode, "config_frozen": config_frozen}


def render_hero(data: Dict, parsed: Dict, is_sample: bool, loaded_file: str) -> None:
    """Render hero section with trust-first headline (Phase 5.4): green for safety."""
    trust = _trust_first_hero_state(data, parsed)
    gate = data.get("execution_gate", {})
    allowed = gate.get("allowed", False)
    as_of = parsed.get("as_of", "")
    
    try:
        ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        time_str = ts.strftime("%b %d, %H:%M")
    except Exception:
        time_str = as_of or "Unknown"
    
    # Phase 5.4: trust-first — green for safety (capital protected or safe trade), amber for review
    # Phase 6.1: run mode in header
    gate_class = "status-allowed" if allowed else "status-blocked"
    gate_text = "ALLOWED" if allowed else "BLOCKED"
    source_class = "status-sample" if is_sample else "status-live"
    source_text = "Sample" if is_sample else "Live"
    hero_headline = trust["headline"]
    run_mode = trust.get("run_mode") or "DRY_RUN"
    st.markdown(f"""
    <div class="hero" style="border-left:4px solid {COLORS['success']};">
        <div style="font-weight:700;font-size:1rem;margin-bottom:0.35rem;">{hero_headline}</div>
        <span class="status-badge {gate_class}">{gate_text}</span>
        <span class="status-badge {source_class}">{source_text}</span>
        <span class="status-badge" style="background:#475569;color:#fff;padding:0.2rem 0.4rem;border-radius:4px;font-size:0.7rem;">{run_mode}</span>
        <span style="color:var(--text-muted);font-size:0.75rem;">📅 {time_str} | 📁 {loaded_file}</span>
    </div>
    """, unsafe_allow_html=True)


def render_trust_section(data: Dict, parsed: Dict) -> None:
    """Phase 5.4: Why-No-Trade summary, top rejection reasons, risk posture badge. Phase 6.1: Config Frozen."""
    trust = _trust_first_hero_state(data, parsed)
    rp = trust["risk_posture"]
    rp_color = COLORS["success"] if rp == "CONSERVATIVE" else (COLORS["warning"] if rp == "BALANCED" else COLORS["danger"])
    st.markdown(f"""
    <div style="margin-bottom:0.75rem;">
        <span style="font-size:0.7rem;color:var(--text-muted);">Risk posture</span>
        <span style="display:inline-block;padding:0.2rem 0.5rem;border-radius:6px;background:{rp_color};color:#fff;font-weight:600;font-size:0.7rem;margin-left:0.35rem;">{rp}</span>
    </div>
    """, unsafe_allow_html=True)
    # Phase 6.1: Config Frozen YES/NO
    if trust.get("config_frozen") is not None:
        frozen_text = "YES" if trust["config_frozen"] else "NO"
        st.markdown(f"**Config frozen:** {frozen_text}")
    daily = data.get("daily_trust_report") or {}
    if daily.get("freeze_violation_changed_keys"):
        st.caption(f"Changed keys (freeze violated): {', '.join(daily['freeze_violation_changed_keys'])}")
    if trust["why_summary"]:
        st.markdown("**Why no trade**")
        st.caption(trust["why_summary"])
    if trust["top_reasons"]:
        st.markdown("**Top blocking reasons**")
        for item in trust["top_reasons"][:5]:
            code = item.get("code", "UNKNOWN")
            count = item.get("count", 0)
            st.caption(f"• {_humanize_label(code)}: {count}")


def render_metrics(parsed: Dict) -> None:
    """Render metric tiles with icons on top."""
    stats = parsed.get("stats", {})
    selected_count = len(parsed.get("selected_signals", []) or [])
    missing_count = len(parsed.get("symbols_without_options", {}) or {})
    exclusion_count = stats.get("total_exclusions", 0)
    candidate_count = stats.get("total_candidates", 0)
    
    metrics = [
        ("Total Symbols", stats.get("total_symbols", 0), "", ""),
        ("Evaluated", stats.get("symbols_evaluated", 0), "", ""),
        ("Candidates", candidate_count, "success" if candidate_count > 0 else "", "success"),
        ("Selected", selected_count, "success" if selected_count > 0 else "", "success"),
        ("Missing Chains", missing_count, "warning" if missing_count > 0 else "", "warning"),
        ("Exclusions", exclusion_count, "danger" if exclusion_count > 10 else "", "danger"),
    ]
    
    cols = st.columns(6)
    for col, (label, value, val_class, tile_class) in zip(cols, metrics):
        with col:
            cfg = METRIC_CONFIG.get(label, {"icon": "📊", "tooltip": label})
            tt = _tooltip(cfg["tooltip"])
            tc = tile_class if value > 0 and tile_class else ""
            vc = val_class if value > 0 and val_class else ""
            st.markdown(f"""
            <div class="metric-tile {tc}">
                <div class="metric-icon">{cfg['icon']}</div>
                <div class="metric-value {vc}">{value}</div>
                <div class="metric-label">{label}{tt}</div>
            </div>
            """, unsafe_allow_html=True)


def render_charts(parsed: Dict, dark: bool) -> None:
    """Render horizontal bar charts with color coding."""
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        has_plotly = True
    except ImportError:
        has_plotly = False
    
    import pandas as pd
    
    c1, c2 = st.columns(2)
    
    # Exclusion Breakdown
    with c1:
        tt = _tooltip(CARD_TOOLTIPS["Exclusion Breakdown"])
        st.markdown(f'<div class="card"><div class="card-title">📊 Exclusion Breakdown{tt}</div>', unsafe_allow_html=True)
        
        exc_summary = ensure_dict(parsed.get("exclusion_summary"))
        rule_counts = ensure_dict(exc_summary.get("rule_counts"))
        if not rule_counts:
            exclusions = ensure_list(parsed.get("exclusions"))
            if exclusions:
                rule_counts = dict(Counter(ensure_dict(e).get("rule", "UNKNOWN") for e in exclusions))
        
        if rule_counts and has_plotly:
            df = pd.DataFrame([
                {"Rule": _humanize_label(r), "Count": c, "Color": EXCLUSION_COLORS.get(r, "#6b7280")}
                for r, c in sorted(rule_counts.items(), key=lambda x: -x[1])
            ])
            fig = go.Figure(go.Bar(
                x=df["Count"], y=df["Rule"], orientation='h',
                marker_color=df["Color"], text=df["Count"], textposition='outside'
            ))
            fig.update_layout(
                height=180, margin=dict(l=0, r=20, t=5, b=5),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=9, color=COLORS["text_dark"] if dark else COLORS["text_light"]),
                showlegend=False, xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
                yaxis=dict(showgrid=False, autorange="reversed")
            )
            st.plotly_chart(fig, use_container_width=True, key="exc_chart")
        elif rule_counts:
            df = pd.DataFrame([{"Rule": _humanize_label(r), "Count": c} for r, c in rule_counts.items()])
            st.bar_chart(df.set_index("Rule"), height=160)
        else:
            st.info("📭 No exclusions")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Candidate Distribution
    with c2:
        tt = _tooltip(CARD_TOOLTIPS["Candidate Distribution"])
        st.markdown(f'<div class="card"><div class="card-title">📈 Candidate Distribution{tt}</div>', unsafe_allow_html=True)
        
        scored = ensure_list(parsed.get("scored_candidates"))
        candidates = [ensure_dict(sc).get("candidate") or {} for sc in scored] if scored else ensure_list(parsed.get("candidates"))
        
        if candidates and has_plotly:
            strategy_counts = Counter(_get_strategy_label(c) for c in candidates if c)
            df = pd.DataFrame([
                {"Strategy": s, "Count": c, "Color": STRATEGY_COLORS.get(s, "#6b7280")}
                for s, c in sorted(strategy_counts.items(), key=lambda x: -x[1])
            ])
            fig = go.Figure(go.Bar(
                x=df["Count"], y=df["Strategy"], orientation='h',
                marker_color=df["Color"], text=df["Count"], textposition='outside'
            ))
            fig.update_layout(
                height=180, margin=dict(l=0, r=20, t=5, b=5),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=9, color=COLORS["text_dark"] if dark else COLORS["text_light"]),
                showlegend=False, xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
                yaxis=dict(showgrid=False, autorange="reversed")
            )
            st.plotly_chart(fig, use_container_width=True, key="dist_chart")
        elif candidates:
            df = pd.DataFrame([{"Strategy": _get_strategy_label(c), "Count": 1} for c in candidates])
            df = df.groupby("Strategy").sum().reset_index()
            st.bar_chart(df.set_index("Strategy"), height=160)
        else:
            st.info("📭 No candidates")
        st.markdown('</div>', unsafe_allow_html=True)


def render_candidates_table(parsed: Dict) -> None:
    """Render candidates table with score percentage."""
    import pandas as pd
    
    tt = _tooltip(CARD_TOOLTIPS["Top Candidates"])
    score_tt = _tooltip("Score based on credit, delta, IV, DTE, liquidity")
    st.markdown(f'<div class="card"><div class="card-title">🎯 Top Candidates{tt}</div>', unsafe_allow_html=True)
    
    scored = parsed.get("scored_candidates", [])
    selected_symbols = {s.get("scored", {}).get("candidate", {}).get("symbol") 
                        for s in (parsed.get("selected_signals", []) or [])}
    
    if scored:
        rows = []
        for sc in scored[:12]:
            cand = sc.get("candidate", {})
            score = _extract_score(sc.get("score", 0))
            symbol = cand.get("symbol", "")
            delta = cand.get("delta")
            iv = cand.get("iv")
            rows.append({
                "Symbol": symbol,
                "Type": _get_strategy_label(cand),
                "Strike": safe_currency(cand.get("strike"), "—"),
                "Exp": cand.get("expiry", "") or cand.get("expiration", ""),
                "Premium": safe_currency(cand.get("mid"), "—"),
                "Delta": safe_delta(delta, "—"),
                "IV": safe_percent(iv, "—"),
                f"Score (0-{int(SCORE_MAX)})": _format_score(score),
                "Selected": "Yes" if symbol in selected_symbols else "",
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=300)
    else:
        candidates = parsed.get("candidates", [])
        if candidates:
            rows = [{
                "Symbol": c.get("symbol", ""),
                "Type": _get_strategy_label(c),
                "Strike": f"${_safe_float(c.get('strike', 0)):,.2f}",
                "Exp": c.get("expiry", "") or c.get("expiration", ""),
                "Premium": f"${_safe_float(c.get('mid', 0)):,.2f}",
            } for c in candidates[:12]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("📭 No candidates. Select a data file.")
    
    st.markdown('</div>', unsafe_allow_html=True)


def render_signals_panel(parsed: Dict) -> None:
    """Render selected signals with Slack messages."""
    with st.expander("📌 Selected Signals", expanded=True):
        selected = parsed.get("selected_signals", []) or []
        if selected:
            for signal in selected:
                scored = signal.get("scored", {})
                cand = scored.get("candidate", {})
                score = _extract_score(scored.get("score", 0))
                strike_raw = cand.get("strike")
                mid_raw = cand.get("mid")
                delta = cand.get("delta")
                strategy = _get_strategy_label(cand)
                strat_class = f"strat-{strategy.lower()}" if strategy.lower() in ["csp", "cc", "put", "call"] else "strat-csp"
                strike_str = safe_currency(strike_raw, "—") if strike_raw is None else f"${_safe_float(strike_raw):,.2f}"
                premium_str = safe_currency(mid_raw, "—")
                delta_str = safe_delta(delta, "—")
                st.markdown(f"""
                <div class="card" style="padding:0.75rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div><strong>{cand.get('symbol', 'N/A')}</strong>
                        <span class="strat-badge {strat_class}">{strategy}</span></div>
                        <span style="font-weight:600;color:var(--success);">{_format_score(score)}</span>
                    </div>
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:0.3rem;">
                        Strike: <b>{strike_str}</b> | Exp: <b>{cand.get('expiry', '') or cand.get('expiration', 'N/A')}</b> |
                        Premium: <b>{premium_str}</b> | Delta: <b>{delta_str}</b>
                    </div>
                    <div class="slack-msg">{_generate_slack_message(cand)}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("📭 No signals selected")


def render_exclusions_panel(parsed: Optional[Dict]) -> None:
    """Render exclusions by rule. Safe when parsed is None or missing keys."""
    import pandas as pd
    
    parsed = ensure_dict(parsed)
    with st.expander("🚫 Exclusions by Rule", expanded=False):
        exc_summary = ensure_dict(parsed.get("exclusion_summary"))
        symbols_by_rule = ensure_dict(exc_summary.get("symbols_by_rule"))
        
        if symbols_by_rule:
            for rule, symbols in list(symbols_by_rule.items()):
                sym_list = ensure_list(symbols)
                st.markdown(f"**{_humanize_label(rule)}** ({len(sym_list)})")
                st.caption(", ".join(str(s) for s in sym_list[:8]) + ("..." if len(sym_list) > 8 else ""))
        else:
            exclusions = ensure_list(parsed.get("exclusions"))
            if exclusions:
                df = pd.DataFrame([
                    {"Symbol": e.get("symbol", ""), "Rule": _humanize_label(e.get("rule", ""))}
                    for e in exclusions[:20]
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("📭 No exclusions")


def render_execution_panel(data: Optional[Dict]) -> None:
    """Render execution plan. Safe when data is None or missing keys."""
    import pandas as pd
    
    data = ensure_dict(data)
    with st.expander("📋 Execution Plan", expanded=False):
        plan = ensure_dict(data.get("execution_plan"))
        orders = ensure_list(plan.get("orders"))
        
        if orders:
            df = pd.DataFrame([{
                "Symbol": o.get("symbol", ""),
                "Action": o.get("action", "").replace("_", " "),
                "Strike": safe_currency(o.get("strike"), "—"),
                "Exp": o.get("expiry", ""),
                "Limit": safe_currency(o.get("limit_price"), "—"),
            } for o in orders])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            reason = plan.get("blocked_reason", "No orders")
            st.warning(f"⚠️ {_humanize_label(reason)}" if reason else "📭 No orders")


# ---------------------------------------------------------------------------
# Test Page - ORATS Live Data
# ---------------------------------------------------------------------------


def render_test_page() -> None:
    """Render the Test page with ORATS Live Data chain fetch."""
    st.markdown("## 🧪 Test Page")
    st.caption("Test ORATS Live Data: expirations and chain via ORATS_API_TOKEN")
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        # Ticker input
        ticker = st.selectbox("Select Symbol", TEST_SYMBOLS, index=0, key="test_ticker")
        custom = st.text_input("Or enter custom symbol", "", key="custom_ticker", placeholder="e.g., SHOP")
        symbol = custom.upper().strip() if custom else ticker
        
        # DTE range - lower defaults to ensure data exists
        dte_col1, dte_col2 = st.columns(2)
        with dte_col1:
            dte_min = st.number_input("DTE Min", value=7, min_value=0, max_value=365, key="dte_min")
        with dte_col2:
            dte_max = st.number_input("DTE Max", value=45, min_value=1, max_value=365, key="dte_max")
        
        st.markdown(f"**Testing: `{symbol}`** (DTE: {dte_min}–{dte_max} days)")
        st.caption("Using bulk endpoints: `list_expirations` → `snapshot_quote_bulk` (all strikes per expiration)")
    
    with c2:
        st.markdown("### Actions")
        webhook_ok, webhook_msg = slack_webhook_available() if SLACK_AVAILABLE else (False, "Slack not configured")
        slack_help = "Send a real test message to Slack" if webhook_ok else "Set SLACK_WEBHOOK_URL to enable Slack alerts"
        fetch_btn = st.button("📥 Fetch Chain", key="fetch_btn", use_container_width=True, help="Fetch via bulk endpoint")
        slack_btn = st.button("💬 Test Slack", key="slack_btn", use_container_width=True, help=slack_help)
        health_btn = st.button("🏥 Health Check", key="health_btn", use_container_width=True, help="Check Theta Terminal connection")
    
    st.markdown("---")
    
    # Health Check
    if health_btn:
        with st.spinner("Checking ORATS..."):
            healthy, message = _orats_health_check()
            if healthy:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")
    
    # Fetch Chain - ORATS Live Data
    if fetch_btn:
        with st.spinner(f"Fetching chain for {symbol} via bulk endpoint..."):
            chain_result = _fetch_real_chain(symbol, dte_min, dte_max)
            
            if chain_result.get("error"):
                st.error(f"❌ {chain_result['error']}")
                if chain_result.get("chain_status"):
                    st.caption(f"Status: {chain_result['chain_status']}")
                if chain_result.get("total_fetched"):
                    st.caption(f"Total contracts fetched (before DTE filter): {chain_result['total_fetched']}")
            else:
                st.success(f"✅ Chain fetched for {symbol}")
                
                # Store in session for Slack test
                st.session_state["test_chain_data"] = chain_result
                
                # Display results
                st.markdown('<div class="test-result">', unsafe_allow_html=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Expirations", chain_result.get("expiration_count", 0))
                with col2:
                    st.metric("Total Contracts", chain_result.get("contract_count", 0))
                with col3:
                    st.metric("Puts", len(chain_result.get("puts", [])))
                with col4:
                    st.metric("Calls", len(chain_result.get("calls", [])))
                
                # Data source and timestamp
                data_src = chain_result.get("data_source", "unknown")
                src_color = "#2aa872" if data_src == "live" else "#6b7280"
                timestamp = chain_result.get("timestamp", "")
                st.markdown(f'<span style="background:{src_color};color:white;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;">Data: {data_src.upper()}</span> <span style="font-size:0.7rem;color:gray;">{timestamp[:19] if timestamp else ""}</span>', unsafe_allow_html=True)
                
                # Show expirations
                expirations = chain_result.get("expirations", [])
                if expirations:
                    st.caption(f"Expirations: {', '.join(expirations[:5])}{'...' if len(expirations) > 5 else ''}")
                
                # Options table with full Greeks
                contracts = chain_result.get("contracts", [])
                if contracts:
                    st.markdown(f"**Options Chain ({len(contracts)} contracts, showing first 20):**")
                    import pandas as pd
                    
                    rows = []
                    for c in contracts[:20]:
                        dte_val = c.get("dte")
                        dte_str = str(dte_val) if dte_val is not None else "—"
                        rows.append({
                            "Strike": safe_currency(c.get("strike"), "—"),
                            "Type": c.get("option_type", c.get("right", "")),
                            "Exp": (c.get("expiration") or "")[:10],
                            "DTE": dte_str,
                            "Bid": safe_currency(c.get("bid"), "—"),
                            "Ask": safe_currency(c.get("ask"), "—"),
                            "IV": safe_percent(c.get("iv"), "—"),
                            "Delta": safe_delta(c.get("delta"), "—"),
                            "Gamma": safe_format(c.get("gamma"), ".4f", "—"),
                            "Theta": safe_format(c.get("theta"), ".4f", "—"),
                        })
                    
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True, hide_index=True, height=350)
                else:
                    st.warning("No contracts returned. Possible causes:")
                    st.markdown("""
                    - Market is closed (no real-time data)
                    - No options in the DTE range [{dte_min}-{dte_max}]
                    - Symbol may not have options
                    - ORATS auth/rate limit (check ORATS_API_TOKEN)
                    """)
                
                st.markdown('</div>', unsafe_allow_html=True)
    
    # Test Slack functionality
    if slack_btn:
        webhook_ok, webhook_msg = slack_webhook_available() if SLACK_AVAILABLE else (False, "Slack not configured")
        if not webhook_ok:
            st.warning("Slack is not configured. Set the **SLACK_WEBHOOK_URL** environment variable to enable alerts, then use **Test Slack** to send a real test message.")
            st.caption(webhook_msg)
        else:
            st.markdown("### Slack Test")
            chain_data = st.session_state.get("test_chain_data", {})
            contracts = chain_data.get("contracts", [])
            if contracts:
                first_contract = contracts[0]
                mock_candidate = {
                    "symbol": first_contract.get("symbol", symbol),
                    "signal_type": "CSP" if first_contract.get("right") == "P" else "CC",
                    "strike": first_contract.get("strike", 100.0),
                    "expiry": first_contract.get("expiration", "2026-02-14"),
                    "mid": first_contract.get("mid") or ((first_contract.get("bid", 0) or 0) + (first_contract.get("ask", 0) or 0)) / 2,
                    "delta": first_contract.get("delta"),
                }
                st.caption("Using real chain data from last fetch")
            else:
                mock_candidate = {
                    "symbol": symbol,
                    "signal_type": "CSP",
                    "strike": 100.0,
                    "expiry": "2026-02-14",
                    "mid": 2.50,
                    "delta": -0.25,
                }
                st.caption("Using mock data (fetch chain first for real data)")
            slack_msg = _generate_slack_message(mock_candidate)
            try:
                import requests
                url = os.getenv("SLACK_WEBHOOK_URL")
                resp = requests.post(
                    url,
                    json={"text": f"*[ChakraOps Test]* {slack_msg}"},
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                resp.raise_for_status()
                st.success("✅ Test message sent to Slack.")
            except Exception as e:
                st.error(f"Failed to send to Slack: {e}")
            st.markdown(f"""
            <div class="card">
                <div class="card-title">💬 Message sent</div>
                <div class="slack-msg">{slack_msg}</div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("View details"):
                st.code(slack_msg.replace("*", "").replace("📊 ", ""))
                st.json(mock_candidate)


def _orats_health_check() -> Tuple[bool, str]:
    """Check ORATS Live Data health."""
    if not ORATS_AVAILABLE or OratsOptionsChainProvider is None:
        return False, "ORATS provider not available (import failed)"
    try:
        provider = OratsOptionsChainProvider()
        status = provider.healthcheck()
        return bool(status.get("ok")), str(status.get("message", "Unknown"))
    except Exception as e:
        return False, str(e)


def _fetch_real_chain(symbol: str, dte_min: int, dte_max: int) -> Dict[str, Any]:
    """Fetch real options chain from ORATS Live Data."""
    if not ORATS_AVAILABLE or OratsOptionsChainProvider is None:
        return {"error": "ORATS provider not available. Set ORATS_API_TOKEN."}
    try:
        from datetime import datetime, timezone
        provider = OratsOptionsChainProvider()
        result = provider.get_full_chain(symbol, dte_min=dte_min, dte_max=dte_max)
        if result.get("chain_status") != "ok":
            return {
                "error": result.get("error", "No chain data"),
                "chain_status": result.get("chain_status", "empty_chain"),
                "data_source": DATA_SOURCE_LIVE,
            }
        contracts = result.get("contracts", [])
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as e:
        return {"error": f"Failed to fetch chain: {str(e)}"}


# ---------------------------------------------------------------------------
# Page Renderers
# ---------------------------------------------------------------------------


def render_dashboard_page(data: Dict, parsed: Dict, is_sample: bool, loaded_file: str) -> None:
    """Render main dashboard."""
    render_hero(data, parsed, is_sample, loaded_file)
    with st.expander("**Trust & discipline**", expanded=True):
        render_trust_section(data, parsed)
    render_metrics(parsed)
    render_charts(parsed, st.session_state.get("dark_mode", False))
    render_candidates_table(parsed)
    render_signals_panel(parsed)
    render_exclusions_panel(parsed)
    render_execution_panel(data)


def render_strategies_page(data: Dict) -> None:
    st.markdown("## 🎯 Strategies")
    st.info("Strategy configuration coming soon.")


def render_analytics_page() -> None:
    st.markdown("## 📈 Analytics")
    st.info("Historical analytics coming soon.")


def render_history_page() -> None:
    import json
    import pandas as pd
    
    st.markdown("## 📜 History")
    
    # C7: Add run selector dropdown with run_id, timestamp, eligible count, shortlisted count
    files = sorted(OUT_DIR.glob("decision_*.json"), reverse=True)[:30]
    
    # Parse run metadata from files
    run_metadata = []
    for f in files:
        if f.name in ("decision_latest.json", "sample_decision.json", "sample_decision_rich.json"):
            continue
        try:
            stat = f.stat()
            # Try to extract run_id and counts from the file
            run_info = {
                "file": f,
                "filename": f.name,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "size_kb": stat.st_size / 1024,
                "run_id": f.stem.replace("decision_", ""),  # Extract timestamp from filename
                "eligible": 0,
                "shortlisted": 0,
                "total": 0,
            }
            
            # Try to read metadata from file header (first few bytes)
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    # Extract counts from the decision snapshot
                    if isinstance(data, dict):
                        run_info["run_id"] = data.get("run_id") or data.get("timestamp") or run_info["run_id"]
                        # Try different paths for counts
                        counts = data.get("counts") or {}
                        if counts:
                            run_info["eligible"] = counts.get("eligible", 0)
                            run_info["shortlisted"] = counts.get("shortlisted", 0)
                            run_info["total"] = counts.get("total", 0)
                        # Alternative: count from symbols list
                        symbols = data.get("symbols") or data.get("evaluated") or []
                        if not counts and isinstance(symbols, list):
                            run_info["total"] = len(symbols)
                            run_info["eligible"] = sum(1 for s in symbols if s.get("verdict") == "ELIGIBLE")
                            run_info["shortlisted"] = sum(1 for s in symbols if s.get("verdict") == "SHORTLISTED")
            except (json.JSONDecodeError, IOError):
                pass
            
            run_metadata.append(run_info)
        except OSError:
            pass
    
    if not run_metadata:
        st.info("No historical evaluation runs found.")
        return
    
    # Run selector dropdown
    st.markdown("### Select a run to view")
    
    run_options = [
        f"{r['modified'].strftime('%Y-%m-%d %H:%M')} — {r['eligible']} eligible, {r['shortlisted']} shortlisted (ID: {r['run_id'][:16] if len(r['run_id']) > 16 else r['run_id']})"
        for r in run_metadata
    ]
    
    selected_idx = st.selectbox(
        "Evaluation Run",
        range(len(run_options)),
        format_func=lambda i: run_options[i],
        key="history_run_selector",
    )
    
    selected_run = run_metadata[selected_idx]
    
    # Display run details
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Symbols", selected_run["total"])
    with col2:
        st.metric("Eligible", selected_run["eligible"])
    with col3:
        st.metric("Shortlisted", selected_run["shortlisted"])
    with col4:
        st.metric("File Size", f"{selected_run['size_kb']:.1f} KB")
    
    # Button to load this run
    if st.button("📂 Load this run", key="history_load_run"):
        st.session_state.selected_snapshot = selected_run["filename"]
        st.session_state.current_page = "dashboard"
        st.rerun()
    
    # Table of all runs
    st.markdown("### All runs")
    rows = []
    for r in run_metadata:
        rows.append({
            "Timestamp": r["modified"].strftime("%Y-%m-%d %H:%M"),
            "Run ID": r["run_id"][:20] + ("…" if len(r["run_id"]) > 20 else ""),
            "Total": r["total"],
            "Eligible": r["eligible"],
            "Shortlisted": r["shortlisted"],
            "Size": f"{r['size_kb']:.1f} KB",
            "File": r["filename"],
        })
    
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_settings_page() -> None:
    st.markdown("## ⚙️ Settings")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### Display")
        st.checkbox("Dark Mode", value=st.session_state.get("dark_mode", False), disabled=True)
        st.checkbox("Show Tooltips", value=True)
    with c2:
        st.markdown("### Data")
        st.text_input("Output Directory", value="out/", disabled=True)
    with c3:
        # D: Show Slack status in Settings/Diagnostics
        st.markdown("### Integrations")
        webhook_ok, webhook_msg = slack_webhook_available() if SLACK_AVAILABLE else (False, "Slack notifier not available")
        if webhook_ok:
            st.success("✅ Slack: **Configured**")
            st.caption("Alerts will be sent to configured webhook.")
        else:
            st.warning("⚠️ Slack: **Not Configured**")
            st.caption("Set `SLACK_WEBHOOK_URL` in `.env` and restart backend to enable alerts.")
            with st.expander("Setup instructions"):
                st.markdown("""
                1. Create a Slack webhook URL at [api.slack.com/apps](https://api.slack.com/apps)
                2. Add to your `.env` file:
                   ```
                   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
                   ```
                3. Restart the backend server
                4. Use the **Test Slack** button on the Test page to verify
                """)


def render_footer() -> None:
    st.markdown("""
    <div class="footer">
        ChakraOps © 2026 — Internal Use Only | 
        <a href="https://github.com/swap2you/chakraops" target="_blank">GitHub</a>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="ChakraOps",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize state
    for key, default in [
        ("dark_mode", False), ("current_page", "dashboard"),
        ("selected_snapshot", None), ("loaded_file", None),
        ("sidebar_collapsed", False), ("load_error", None)
    ]:
        if key not in st.session_state:
            st.session_state[key] = default
    
    # Get files and load data
    files = get_available_snapshots() or ["No files"]
    data, is_sample, loaded_file, error = load_decision_data(st.session_state.selected_snapshot)
    st.session_state.loaded_file = loaded_file
    parsed = parse_snapshot(data)
    
    # Inject CSS
    inject_premium_css(st.session_state.dark_mode, st.session_state.sidebar_collapsed)
    
    # Header - pass actual data_source from loaded data
    data_source = parsed.get("data_source", "unknown")
    new_dark, new_file, refresh = render_header(is_sample, loaded_file, files, data_source)
    if error:
        st.warning(f"⚠️ {error}")
    
    # Sidebar
    selected_page, new_collapsed = render_sidebar(st.session_state.current_page, st.session_state.sidebar_collapsed)
    
    # Handle state changes
    rerun = False
    if selected_page != st.session_state.current_page:
        st.session_state.current_page = selected_page
        rerun = True
    if new_dark != st.session_state.dark_mode:
        st.session_state.dark_mode = new_dark
        rerun = True
    if new_collapsed != st.session_state.sidebar_collapsed:
        st.session_state.sidebar_collapsed = new_collapsed
        rerun = True
    if new_file:
        st.session_state.selected_snapshot = new_file
        rerun = True
    if refresh:
        rerun = True
    
    if rerun:
        st.rerun()
    
    # Render page
    page = st.session_state.current_page
    if page == "dashboard":
        render_dashboard_page(data, parsed, is_sample, loaded_file)
    elif page == "positions":
        from app.ui.position_manager_ui import render_positions_page
        render_positions_page(data, parsed)
    elif page == "test":
        render_test_page()
    elif page == "strategies":
        render_strategies_page(data)
    elif page == "analytics":
        render_analytics_page()
    elif page == "history":
        render_history_page()
    elif page == "settings":
        render_settings_page()
    
    render_footer()


if __name__ == "__main__":
    main()
