# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Premium ChakraOps Dashboard — Option Alpha-style trading platform UI.

A modern, professional trading dashboard with:
- Top header bar with logo, controls, and data source selector
- Streamlined sidebar navigation (icons visible when collapsed)
- Hero section with decision status and key metrics
- Plotly charts for exclusion analysis and candidate distribution
- Detailed tables with proper formatting
- Simulated Slack messages for selected signals
- Functional data loading from selected snapshot files
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUT_DIR = Path("out")
DECISION_LATEST = OUT_DIR / "decision_latest.json"
SAMPLE_DECISION_RICH = OUT_DIR / "sample_decision_rich.json"
SAMPLE_DECISION = OUT_DIR / "sample_decision.json"

NAV_ITEMS = [
    ("Dashboard", "dashboard", "📊"),
    ("Strategies", "strategies", "🎯"),
    ("Analytics", "analytics", "📈"),
    ("History", "history", "📜"),
    ("Settings", "settings", "⚙️"),
]

# Color palette - refined with better contrast
COLORS = {
    "primary": "#005ea6",      # Slightly lighter accent for header
    "primary_dark": "#004580",
    "success": "#2aa872",
    "success_border": "#1e8a5e",
    "warning": "#e0a800",
    "warning_border": "#c49300",
    "danger": "#d9534f",
    "danger_border": "#c9302c",
    "neutral": "#6c757d",
    "surface_light": "#ffffff",
    "surface_dark": "#1a1f2e",
    "bg_light": "#f5f7fa",
    "bg_dark": "#0d1117",
    "text_light": "#24292f",
    "text_dark": "#e6edf3",
    "border_light": "#e1e4e8",
    "border_dark": "#30363d",
}

# Metric tooltips with detailed explanations
METRIC_TOOLTIPS = {
    "Total Symbols": "Total number of symbols in the trading universe being monitored",
    "Evaluated": "Symbols that passed initial screening and were evaluated for options chains",
    "Candidates": "Option positions that passed all filters and are available for selection",
    "Selected": "Top-ranked candidates chosen by the scoring algorithm for potential execution",
    "Missing Chains": "Symbols without available options data (market closed, no chains, or API errors)",
    "Exclusions": "Total filter rejections across all symbols (spread too wide, delta out of range, etc.)",
}

# Card tooltips
CARD_TOOLTIPS = {
    "Exclusion Breakdown": "Count of symbols rejected by each filter rule during the screening process",
    "Candidate Distribution": "Distribution of candidates by strategy type (CSP = Cash-Secured Put, CC = Covered Call)",
    "Top Candidates": "Highest-scoring option positions after all filters, ranked by the scoring algorithm",
    "Selected Signals": "Signals chosen for potential execution with simulated Slack alert messages",
    "Exclusions by Rule": "Detailed breakdown of which symbols were rejected and why",
    "Execution Plan": "Generated orders ready for execution (or reason why execution is blocked)",
}


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------


def get_available_snapshots() -> List[str]:
    """Get list of available snapshot files in out/ directory."""
    if not OUT_DIR.exists():
        return []
    
    files = []
    # Add sample files first (if they exist)
    if SAMPLE_DECISION_RICH.exists():
        files.append(SAMPLE_DECISION_RICH.name)
    if SAMPLE_DECISION.exists():
        files.append(SAMPLE_DECISION.name)
    if DECISION_LATEST.exists():
        files.insert(0, DECISION_LATEST.name)  # Latest at top
    
    # Add timestamped decision files
    for f in sorted(OUT_DIR.glob("decision_*.json"), reverse=True):
        if f.name not in files and f.name not in ("decision_latest.json", "sample_decision.json", "sample_decision_rich.json"):
            files.append(f.name)
    
    return files[:20]  # Limit to 20 files


def load_decision_data(filename: Optional[str] = None) -> Tuple[Dict[str, Any], bool, str]:
    """Load decision data from specified file or auto-detect.
    
    Args:
        filename: Specific file to load, or None to auto-detect
        
    Returns:
        Tuple of (data dict, is_sample_data boolean, loaded_filename)
    """
    # If specific file requested
    if filename:
        filepath = OUT_DIR / filename
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                is_sample = "sample" in filename.lower()
                return data, is_sample, filename
            except (json.JSONDecodeError, IOError):
                pass
    
    # Auto-detect: Try decision_latest.json first
    if DECISION_LATEST.exists():
        try:
            with open(DECISION_LATEST, "r", encoding="utf-8") as f:
                data = json.load(f)
            snapshot = data.get("decision_snapshot", {})
            if snapshot.get("stats", {}).get("total_symbols", 0) > 0:
                return data, False, DECISION_LATEST.name
        except (json.JSONDecodeError, IOError):
            pass
    
    # Try rich sample data
    if SAMPLE_DECISION_RICH.exists():
        try:
            with open(SAMPLE_DECISION_RICH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, True, SAMPLE_DECISION_RICH.name
        except (json.JSONDecodeError, IOError):
            pass
    
    # Fall back to basic sample data
    if SAMPLE_DECISION.exists():
        try:
            with open(SAMPLE_DECISION, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, True, SAMPLE_DECISION.name
        except (json.JSONDecodeError, IOError):
            pass
    
    # Return empty structure if nothing found
    return {
        "decision_snapshot": {
            "stats": {},
            "candidates": [],
            "selected_signals": [],
            "exclusions": [],
            "symbols_with_options": [],
            "symbols_without_options": {},
            "data_source": "unavailable",
        },
        "execution_gate": {"allowed": False, "reasons": ["No data available"]},
        "execution_plan": {"orders": []},
        "metadata": {},
    }, True, "none"


def parse_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse decision snapshot into component parts."""
    snapshot = data.get("decision_snapshot", {})
    return {
        "stats": snapshot.get("stats", {}),
        "candidates": snapshot.get("candidates", []),
        "scored_candidates": snapshot.get("scored_candidates", []),
        "selected_signals": snapshot.get("selected_signals", []),
        "exclusions": snapshot.get("exclusions", []),
        "exclusion_summary": snapshot.get("exclusion_summary", {}),
        "symbols_with_options": snapshot.get("symbols_with_options", []),
        "symbols_without_options": snapshot.get("symbols_without_options", {}),
        "data_source": snapshot.get("data_source", "unknown"),
        "as_of": snapshot.get("as_of", ""),
        "pipeline_timestamp": snapshot.get("pipeline_timestamp", ""),
    }


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _extract_score(score_val: Any) -> float:
    """Extract numeric score from dict or float."""
    if score_val is None:
        return 0.0
    if isinstance(score_val, dict):
        return _safe_float(score_val.get("total", 0))
    return _safe_float(score_val)


def _get_strategy_label(candidate: Dict[str, Any]) -> str:
    """Get strategy label from candidate data."""
    signal_type = candidate.get("signal_type", "")
    if signal_type and signal_type not in ("", "Unknown"):
        return signal_type
    
    strategy = candidate.get("strategy", "")
    if strategy and strategy not in ("", "Unknown"):
        return strategy
    
    option_type = candidate.get("option_type", "")
    if option_type:
        if option_type.upper() in ("PUT", "P"):
            return "PUT"
        elif option_type.upper() in ("CALL", "C"):
            return "CALL"
    
    right = candidate.get("right", "")
    if right:
        if right.upper() in ("P", "PUT"):
            return "PUT"
        elif right.upper() in ("C", "CALL"):
            return "CALL"
    
    return "Other"


def _humanize_label(key: str) -> str:
    """Convert snake_case to Title Case."""
    if not key:
        return key
    return " ".join(w.capitalize() for w in str(key).replace("_", " ").replace("-", " ").split())


def _generate_slack_message(candidate: Dict[str, Any]) -> str:
    """Generate a simulated Slack alert message for a signal."""
    symbol = candidate.get("symbol", "???")
    strike = _safe_float(candidate.get("strike", 0))
    expiry = candidate.get("expiry", "") or candidate.get("expiration", "N/A")
    mid = _safe_float(candidate.get("mid", 0))
    signal_type = _get_strategy_label(candidate)
    
    option_char = "P" if signal_type in ("CSP", "PUT") else "C"
    
    return f"📊 *SELL 1 {symbol} ${strike:.0f}{option_char}* expiring {expiry} @ *${mid:.2f}* credit"


# ---------------------------------------------------------------------------
# Theme CSS Injection
# ---------------------------------------------------------------------------


def inject_premium_css(dark: bool = False) -> None:
    """Inject premium dashboard CSS with modern styling."""
    bg = COLORS["bg_dark"] if dark else COLORS["bg_light"]
    surface = COLORS["surface_dark"] if dark else COLORS["surface_light"]
    text = COLORS["text_dark"] if dark else COLORS["text_light"]
    text_muted = "#8b949e" if dark else "#57606a"
    border = COLORS["border_dark"] if dark else COLORS["border_light"]
    
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    :root {{
        --bg-primary: {bg};
        --bg-surface: {surface};
        --border-color: {border};
        --text-primary: {text};
        --text-secondary: {text_muted};
        --primary: {COLORS['primary']};
        --success: {COLORS['success']};
        --success-border: {COLORS['success_border']};
        --danger: {COLORS['danger']};
        --danger-border: {COLORS['danger_border']};
        --warning: {COLORS['warning']};
        --warning-border: {COLORS['warning_border']};
    }}
    
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    
    .stApp {{ background: var(--bg-primary); }}
    .main .block-container {{ max-width: 1400px; padding: 0.5rem 2rem 2rem; }}
    
    /* Hide Streamlit branding */
    #MainMenu, footer {{ visibility: hidden; }}
    header[data-testid="stHeader"] {{ display: none; }}
    
    /* Sidebar toggle fix - ALWAYS visible at fixed position */
    [data-testid="collapsedControl"] {{
        position: fixed !important;
        left: 10px !important;
        top: 50px !important;
        z-index: 999999 !important;
        background: {'#1e293b' if dark else '#ffffff'} !important;
        border: 1px solid {'#30363d' if dark else '#e1e4e8'} !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        padding: 4px !important;
    }}
    
    [data-testid="collapsedControl"] svg {{
        color: {'#e6edf3' if dark else '#24292f'} !important;
    }}
    
    /* Sidebar styling - narrower */
    [data-testid="stSidebar"] {{
        width: 220px !important;
        min-width: 220px !important;
        background: {'#0f172a' if dark else '#1e293b'} !important;
    }}
    
    [data-testid="stSidebar"] > div:first-child {{
        padding-top: 0.75rem;
        width: 220px !important;
    }}
    
    [data-testid="stSidebar"] .stMarkdown {{
        color: #e2e8f0;
    }}
    
    /* Nav buttons in sidebar */
    [data-testid="stSidebar"] .stButton > button {{
        background: transparent !important;
        color: #94a3b8 !important;
        border: none !important;
        text-align: left !important;
        padding: 0.5rem 0.75rem !important;
        font-size: 0.85rem !important;
        transition: all 0.15s ease !important;
    }}
    
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(255,255,255,0.1) !important;
        color: #ffffff !important;
    }}
    
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background: rgba(0,94,166,0.3) !important;
        color: #60a5fa !important;
        border-left: 3px solid #3b82f6 !important;
    }}
    
    /* Top header bar - refined gradient */
    .top-header {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_dark']} 100%);
        padding: 0.75rem 1.25rem;
        margin: -0.5rem -2rem 1.25rem -2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 2px 12px rgba(0,0,0,0.12);
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }}
    
    .header-brand {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }}
    
    .header-logo {{
        width: 38px;
        height: 38px;
        background: rgba(255,255,255,0.15);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
    }}
    
    .header-title {{
        color: white;
        font-size: 1.35rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.02em;
    }}
    
    .header-subtitle {{
        color: rgba(255,255,255,0.65);
        font-size: 0.7rem;
        margin: 0;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    
    .header-controls {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }}
    
    .header-badge {{
        background: rgba(255,255,255,0.15);
        color: white;
        padding: 0.35rem 0.75rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 500;
        backdrop-filter: blur(4px);
    }}
    
    /* Info icon styling */
    .info-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: {'rgba(255,255,255,0.1)' if dark else 'rgba(0,94,166,0.1)'};
        color: {COLORS['primary']};
        font-size: 0.7rem;
        font-weight: 600;
        cursor: help;
        margin-left: 6px;
        transition: all 0.15s ease;
    }}
    
    .info-icon:hover {{
        background: {'rgba(255,255,255,0.2)' if dark else 'rgba(0,94,166,0.2)'};
        transform: scale(1.1);
    }}
    
    /* Premium card styling with better shadows */
    .premium-card {{
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.02);
    }}
    
    .card-header {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--border-color);
    }}
    
    .card-title {{
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text-primary);
        margin: 0;
    }}
    
    /* Hero section */
    .hero-section {{
        background: linear-gradient(135deg, var(--bg-surface) 0%, {'#1a1f2e' if dark else '#f0f4f8'} 100%);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    
    .hero-status {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-wrap: wrap;
    }}
    
    .status-badge {{
        display: inline-flex;
        align-items: center;
        padding: 0.45rem 0.9rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.8rem;
    }}
    
    .status-allowed {{ background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }}
    .status-blocked {{ background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }}
    .status-live {{ background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }}
    .status-snapshot {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}
    .status-sample {{ background: #f3f4f6; color: #374151; border: 1px solid #e5e7eb; }}
    
    /* Metrics with colored borders */
    .metric-tile {{
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 0.9rem;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.03);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    
    .metric-tile:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }}
    
    .metric-tile.success {{ border-left: 4px solid var(--success-border); }}
    .metric-tile.warning {{ border-left: 4px solid var(--warning-border); }}
    .metric-tile.danger {{ border-left: 4px solid var(--danger-border); }}
    
    .metric-value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1.2;
    }}
    
    .metric-value.success {{ color: var(--success); }}
    .metric-value.warning {{ color: var(--warning); }}
    .metric-value.danger {{ color: var(--danger); }}
    
    .metric-label {{
        font-size: 0.65rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.35rem;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.25rem;
    }}
    
    /* Slack message simulation - monospace font */
    .slack-message {{
        background: {'#2d333b' if dark else '#f8f9fa'};
        border-left: 4px solid {COLORS['primary']};
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
        border-radius: 0 8px 8px 0;
        font-family: 'JetBrains Mono', 'Monaco', 'Menlo', monospace;
        font-size: 0.78rem;
        color: var(--text-primary);
        line-height: 1.5;
    }}
    
    /* Strategy badges */
    .strategy-badge {{
        display: inline-block;
        padding: 0.2rem 0.5rem;
        border-radius: 6px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }}
    
    .strategy-csp {{ background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }}
    .strategy-cc {{ background: #f3e8ff; color: #7c3aed; border: 1px solid #e9d5ff; }}
    .strategy-put {{ background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }}
    .strategy-call {{ background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }}
    
    /* Tables */
    .stDataFrame {{
        border-radius: 12px;
        overflow: hidden;
    }}
    
    div[data-testid="stDataFrameResizable"] {{
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }}
    
    /* Expander */
    .streamlit-expanderHeader {{
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        font-weight: 500 !important;
    }}
    
    /* Footer */
    .dashboard-footer {{
        margin-top: 2rem;
        padding: 0.75rem;
        text-align: center;
        color: var(--text-secondary);
        font-size: 0.7rem;
    }}
    
    /* Selectbox in header styling */
    .header-select {{
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 6px;
        color: white;
        padding: 0.35rem 0.5rem;
        font-size: 0.75rem;
        min-width: 140px;
    }}
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Component Renderers
# ---------------------------------------------------------------------------


def render_top_header(is_sample: bool, dark: bool, current_file: str, available_files: List[str]) -> Tuple[bool, Optional[str], bool]:
    """Render the top header bar with controls.
    
    Returns tuple of (new_dark_mode, selected_file_if_changed, refresh_clicked)
    """
    # Create header using markdown for the brand section
    st.markdown(f"""
    <div class="top-header">
        <div class="header-brand">
            <div class="header-logo">⚡</div>
            <div>
                <p class="header-title">ChakraOps Dashboard</p>
                <p class="header-subtitle">Options Trading Platform</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Controls row
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
    
    with col1:
        # Data source selector
        current_idx = 0
        if current_file in available_files:
            current_idx = available_files.index(current_file)
        
        selected_file = st.selectbox(
            "📁 Data Source",
            available_files,
            index=current_idx,
            key="header_file_selector",
            label_visibility="collapsed",
            help="Select a snapshot file to load"
        )
    
    with col2:
        if is_sample:
            st.markdown('<span class="header-badge" style="background: #6b7280;">📊 Sample</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="header-badge" style="background: #2aa872;">✓ Live</span>', unsafe_allow_html=True)
    
    with col3:
        new_dark = st.toggle("🌙", value=dark, key="header_dark_toggle", help="Toggle dark mode")
    
    with col4:
        refresh_clicked = st.button("🔄 Refresh", key="header_refresh", help="Reload data from selected file")
    
    # Determine if file changed
    file_changed = selected_file != current_file
    
    return new_dark, selected_file if file_changed else None, refresh_clicked


def render_sidebar(current_page: str, collapsed: bool = False) -> str:
    """Render the streamlined sidebar with navigation only.
    
    Returns the selected page.
    """
    with st.sidebar:
        st.markdown("""
        <div style="padding: 0.25rem 0.5rem; margin-bottom: 0.75rem;">
            <h2 style="color: white; font-size: 1.1rem; font-weight: 700; margin: 0;">
                ⚡ ChakraOps
            </h2>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<p style="color: #64748b; font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.4rem; padding-left: 0.5rem;">Navigation</p>', unsafe_allow_html=True)
        
        selected_page = current_page
        for label, page_id, icon in NAV_ITEMS:
            is_active = page_id == current_page
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{page_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                selected_page = page_id
        
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 0.75rem 0;'>", unsafe_allow_html=True)
        
        # Quick stats
        st.markdown('<p style="color: #64748b; font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.4rem; padding-left: 0.5rem;">Status</p>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="padding: 0.5rem; background: rgba(255,255,255,0.05); border-radius: 8px; font-size: 0.75rem; color: #94a3b8;">
            <div style="margin-bottom: 0.25rem;">🕐 Last refresh: just now</div>
            <div>📡 Connection: Active</div>
        </div>
        """, unsafe_allow_html=True)
    
    return selected_page


def render_hero(data: Dict[str, Any], parsed: Dict[str, Any], is_sample: bool, dark: bool, loaded_file: str) -> None:
    """Render the hero section with status and metrics."""
    gate = data.get("execution_gate", {})
    gate_allowed = gate.get("allowed", False)
    stats = parsed["stats"]
    data_source = parsed["data_source"]
    as_of = parsed.get("as_of", "")
    symbols_without = parsed.get("symbols_without_options", {})
    
    # Format timestamp
    try:
        ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        formatted_time = ts.strftime("%b %d, %Y %H:%M")
    except (ValueError, AttributeError):
        formatted_time = as_of or "Unknown"
    
    gate_status = "ALLOWED" if gate_allowed else "BLOCKED"
    gate_class = "status-allowed" if gate_allowed else "status-blocked"
    source_class = "status-sample" if is_sample else ("status-live" if data_source == "live" else "status-snapshot")
    source_label = "Sample Data" if is_sample else ("Live" if data_source == "live" else "Snapshot")
    
    st.markdown(f"""
    <div class="hero-section">
        <div class="hero-status">
            <span class="status-badge {gate_class}">{gate_status}</span>
            <span class="status-badge {source_class}">{source_label}</span>
            <span style="color: var(--text-secondary); font-size: 0.8rem;">
                📅 {formatted_time}
            </span>
            <span style="color: var(--text-secondary); font-size: 0.75rem; opacity: 0.7;">
                | File: {loaded_file}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Metrics in a responsive grid
    selected_count = len(parsed.get("selected_signals", []) or [])
    missing_count = len(symbols_without) if isinstance(symbols_without, dict) else 0
    exclusion_count = stats.get("total_exclusions", 0)
    candidate_count = stats.get("total_candidates", 0)
    
    cols = st.columns(6)
    
    metrics = [
        ("Total Symbols", stats.get("total_symbols", 0), "", ""),
        ("Evaluated", stats.get("symbols_evaluated", 0), "", ""),
        ("Candidates", candidate_count, "success" if candidate_count > 0 else "", "success" if candidate_count > 0 else ""),
        ("Selected", selected_count, "success" if selected_count > 0 else "", "success" if selected_count > 0 else ""),
        ("Missing Chains", missing_count, "warning" if missing_count > 0 else "", "warning" if missing_count > 0 else ""),
        ("Exclusions", exclusion_count, "danger" if exclusion_count > 10 else ("warning" if exclusion_count > 5 else ""), "danger" if exclusion_count > 10 else ("warning" if exclusion_count > 5 else "")),
    ]
    
    for col, (label, value, color_class, border_class) in zip(cols, metrics):
        with col:
            tooltip = METRIC_TOOLTIPS.get(label, "")
            st.markdown(f"""
            <div class="metric-tile {border_class}" title="{tooltip}">
                <div class="metric-value {color_class}">{value}</div>
                <div class="metric-label">
                    {label}
                    <span class="info-icon" title="{tooltip}">?</span>
                </div>
            </div>
            """, unsafe_allow_html=True)


def render_charts(parsed: Dict[str, Any], dark: bool) -> None:
    """Render charts using Plotly for better customization."""
    try:
        import plotly.express as px
        has_plotly = True
    except ImportError:
        has_plotly = False
    
    import pandas as pd
    
    col1, col2 = st.columns(2)
    
    with col1:
        tooltip = CARD_TOOLTIPS.get("Exclusion Breakdown", "")
        st.markdown(f"""
        <div class="premium-card">
            <div class="card-header">
                <h3 class="card-title">📊 Exclusion Breakdown</h3>
                <span class="info-icon" title="{tooltip}">?</span>
            </div>
        """, unsafe_allow_html=True)
        
        exclusion_summary = parsed.get("exclusion_summary", {})
        rule_counts = exclusion_summary.get("rule_counts", {})
        
        # Also try to build from raw exclusions if summary not available
        if not rule_counts:
            exclusions = parsed.get("exclusions", [])
            if exclusions:
                rule_counts = Counter(e.get("rule", "UNKNOWN") for e in exclusions)
        
        if rule_counts and has_plotly:
            df = pd.DataFrame([
                {"Rule": _humanize_label(rule), "Count": count}
                for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])
            ])
            
            fig = px.bar(
                df, x="Count", y="Rule", orientation="h",
                color_discrete_sequence=[COLORS["danger"]],
            )
            fig.update_layout(
                height=220,
                margin=dict(l=0, r=0, t=5, b=5),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=10, color=COLORS["text_dark"] if dark else COLORS["text_light"]),
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                yaxis=dict(showgrid=False),
            )
            st.plotly_chart(fig, use_container_width=True, key="exclusion_chart")
        elif rule_counts:
            df = pd.DataFrame([
                {"Rule": _humanize_label(rule), "Count": count}
                for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])
            ])
            st.bar_chart(df.set_index("Rule"), use_container_width=True, height=200)
        else:
            st.info("No exclusion data available")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        tooltip = CARD_TOOLTIPS.get("Candidate Distribution", "")
        st.markdown(f"""
        <div class="premium-card">
            <div class="card-header">
                <h3 class="card-title">📈 Candidate Distribution</h3>
                <span class="info-icon" title="{tooltip}">?</span>
            </div>
        """, unsafe_allow_html=True)
        
        candidates = parsed.get("candidates", [])
        scored_candidates = parsed.get("scored_candidates", [])
        
        all_candidates = []
        if scored_candidates:
            for sc in scored_candidates:
                cand = sc.get("candidate", {})
                if cand:
                    all_candidates.append(cand)
        elif candidates:
            all_candidates = candidates
        
        if all_candidates and has_plotly:
            strategy_counts: Dict[str, int] = {}
            for c in all_candidates:
                label = _get_strategy_label(c)
                strategy_counts[label] = strategy_counts.get(label, 0) + 1
            
            df = pd.DataFrame([
                {"Strategy": stype, "Count": count}
                for stype, count in sorted(strategy_counts.items(), key=lambda x: -x[1])
            ])
            
            colors = {
                "CSP": COLORS["primary"], 
                "CC": "#7c3aed", 
                "PUT": COLORS["danger"], 
                "CALL": COLORS["success"], 
                "Other": COLORS["neutral"]
            }
            
            fig = px.bar(
                df, x="Strategy", y="Count",
                color="Strategy",
                color_discrete_map=colors,
            )
            fig.update_layout(
                height=220,
                margin=dict(l=0, r=0, t=5, b=5),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=10, color=COLORS["text_dark"] if dark else COLORS["text_light"]),
                showlegend=False,
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            )
            st.plotly_chart(fig, use_container_width=True, key="distribution_chart")
        elif all_candidates:
            strategy_counts = Counter(_get_strategy_label(c) for c in all_candidates)
            df = pd.DataFrame([
                {"Strategy": s, "Count": c} for s, c in strategy_counts.items()
            ])
            st.bar_chart(df.set_index("Strategy"), use_container_width=True, height=200)
        else:
            st.info("No candidate data available")
        
        st.markdown('</div>', unsafe_allow_html=True)


def render_candidates_table(parsed: Dict[str, Any], dark: bool) -> None:
    """Render the candidates table."""
    import pandas as pd
    
    tooltip = CARD_TOOLTIPS.get("Top Candidates", "")
    st.markdown(f"""
    <div class="premium-card">
        <div class="card-header">
            <h3 class="card-title">🎯 Top Candidates</h3>
            <span class="info-icon" title="{tooltip}">?</span>
        </div>
    """, unsafe_allow_html=True)
    
    scored = parsed.get("scored_candidates", [])
    selected_symbols = {
        s.get("scored", {}).get("candidate", {}).get("symbol")
        for s in (parsed.get("selected_signals", []) or [])
    }
    
    if scored:
        rows = []
        for sc in scored[:15]:
            candidate = sc.get("candidate", {})
            score_val = sc.get("score", 0)
            score_total = _extract_score(score_val)
            symbol = candidate.get("symbol", "")
            
            strike = _safe_float(candidate.get("strike", 0))
            mid = _safe_float(candidate.get("mid", 0))
            delta = candidate.get("delta")
            iv = candidate.get("iv")
            
            rows.append({
                "Symbol": symbol,
                "Type": _get_strategy_label(candidate),
                "Strike": f"${strike:,.2f}",
                "Expiration": candidate.get("expiry", "") or candidate.get("expiration", ""),
                "Premium": f"${mid:,.2f}",
                "Delta": f"{_safe_float(delta):.2f}" if delta is not None else "—",
                "IV": f"{_safe_float(iv) * 100:.1f}%" if iv is not None else "—",
                "Score": f"{score_total:.2f}",
                "✓": "✅" if symbol in selected_symbols else "",
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
    else:
        candidates = parsed.get("candidates", [])
        if candidates:
            rows = []
            for c in candidates[:15]:
                strike = _safe_float(c.get("strike", 0))
                mid = _safe_float(c.get("mid", 0))
                delta = c.get("delta")
                iv = c.get("iv")
                
                rows.append({
                    "Symbol": c.get("symbol", ""),
                    "Type": _get_strategy_label(c),
                    "Strike": f"${strike:,.2f}",
                    "Expiration": c.get("expiry", "") or c.get("expiration", ""),
                    "Premium": f"${mid:,.2f}",
                    "Delta": f"{_safe_float(delta):.2f}" if delta is not None else "—",
                    "IV": f"{_safe_float(iv) * 100:.1f}%" if iv is not None else "—",
                })
            
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No candidates to display. Select a data file with candidate data.")
    
    st.markdown('</div>', unsafe_allow_html=True)


def render_detail_panels(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render expandable detail panels with Slack simulation."""
    import pandas as pd
    
    # Selected Signals Panel with Slack simulation
    tooltip = CARD_TOOLTIPS.get("Selected Signals", "")
    with st.expander(f"📌 Selected Signals & Slack Alerts", expanded=True):
        st.markdown(f'<small style="color: var(--text-secondary);">{tooltip}</small>', unsafe_allow_html=True)
        
        selected = parsed.get("selected_signals", []) or []
        if selected:
            for i, signal in enumerate(selected):
                scored = signal.get("scored", {})
                candidate = scored.get("candidate", {})
                score_val = scored.get("score", 0)
                score_total = _extract_score(score_val)
                
                strike = _safe_float(candidate.get("strike", 0))
                mid = _safe_float(candidate.get("mid", 0))
                delta = candidate.get("delta")
                delta_str = f"{_safe_float(delta):.2f}" if delta is not None else "N/A"
                strategy = _get_strategy_label(candidate)
                
                strategy_class = "strategy-csp" if strategy == "CSP" else ("strategy-cc" if strategy == "CC" else "strategy-put")
                
                st.markdown(f"""
                <div class="premium-card" style="margin-bottom: 0.75rem; padding: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="font-size: 1.05rem;">{candidate.get('symbol', 'N/A')}</strong>
                            <span class="strategy-badge {strategy_class}" style="margin-left: 0.5rem;">{strategy}</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-weight: 600; color: var(--success);">Score: {score_total:.2f}</span>
                        </div>
                    </div>
                    <div style="margin-top: 0.4rem; font-size: 0.8rem; color: var(--text-secondary);">
                        Strike: <strong>${strike:,.2f}</strong> | 
                        Expiry: <strong>{candidate.get('expiry', '') or candidate.get('expiration', 'N/A')}</strong> | 
                        Premium: <strong>${mid:.2f}</strong> |
                        Delta: <strong>{delta_str}</strong>
                    </div>
                    <div class="slack-message">
                        {_generate_slack_message(candidate)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No signals selected in this snapshot")
    
    # Exclusions Panel
    tooltip = CARD_TOOLTIPS.get("Exclusions by Rule", "")
    with st.expander(f"🚫 Exclusions by Rule", expanded=False):
        st.markdown(f'<small style="color: var(--text-secondary);">{tooltip}</small>', unsafe_allow_html=True)
        
        exclusion_summary = parsed.get("exclusion_summary", {})
        symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
        
        if symbols_by_rule:
            for rule, symbols in symbols_by_rule.items():
                st.markdown(f"**{_humanize_label(rule)}** ({len(symbols)} symbols)")
                st.markdown(f"<span style='color: var(--text-secondary); font-size: 0.8rem;'>{', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}</span>", unsafe_allow_html=True)
                st.markdown("<hr style='margin: 0.4rem 0; opacity: 0.2;'>", unsafe_allow_html=True)
        else:
            exclusions = parsed.get("exclusions", [])
            if exclusions:
                df = pd.DataFrame([
                    {"Symbol": e.get("symbol", ""), "Rule": _humanize_label(e.get("rule", "")), "Message": e.get("message", "")}
                    for e in exclusions[:30]
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No exclusions recorded in this snapshot")
    
    # Execution Plan Panel
    tooltip = CARD_TOOLTIPS.get("Execution Plan", "")
    with st.expander(f"📋 Execution Plan", expanded=False):
        st.markdown(f'<small style="color: var(--text-secondary);">{tooltip}</small>', unsafe_allow_html=True)
        
        plan = data.get("execution_plan", {})
        orders = plan.get("orders", [])
        
        if orders:
            df = pd.DataFrame([
                {
                    "Symbol": o.get("symbol", ""),
                    "Action": o.get("action", "").replace("_", " "),
                    "Qty": o.get("quantity", 1),
                    "Strike": f"${_safe_float(o.get('strike', 0)):,.2f}",
                    "Expiry": o.get("expiry", ""),
                    "Type": o.get("option_type", ""),
                    "Limit": f"${_safe_float(o.get('limit_price', 0)):,.2f}",
                }
                for o in orders
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            blocked_reason = plan.get("blocked_reason", "No orders generated")
            if blocked_reason:
                st.warning(f"Execution blocked: {_humanize_label(blocked_reason)}")
            else:
                st.info("No orders in execution plan")


def render_footer() -> None:
    """Render a simplified footer."""
    st.markdown("""
    <div class="dashboard-footer">
        ChakraOps © 2026 — Internal Use Only
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page Renderers
# ---------------------------------------------------------------------------


def render_dashboard_page(data: Dict[str, Any], parsed: Dict[str, Any], is_sample: bool, dark: bool, loaded_file: str) -> None:
    """Render the main dashboard page."""
    render_hero(data, parsed, is_sample, dark, loaded_file)
    render_charts(parsed, dark)
    render_candidates_table(parsed, dark)
    render_detail_panels(data, parsed, dark)


def render_strategies_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the strategies page."""
    st.markdown("## 🎯 Strategies")
    st.info("Strategy configuration and analysis coming soon.")
    
    with st.expander("📊 Current Configuration"):
        configs = data.get("decision_snapshot", {}).get("configs", {})
        if configs:
            st.json(configs)
        else:
            st.write("No configuration data available")


def render_analytics_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the analytics page."""
    st.markdown("## 📈 Analytics")
    st.info("Historical analytics and performance tracking coming soon.")


def render_history_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the history page."""
    import pandas as pd
    
    st.markdown("## 📜 History")
    
    snapshot_files = sorted(OUT_DIR.glob("decision_*.json"), reverse=True)[:20]
    
    if snapshot_files:
        rows = []
        for f in snapshot_files:
            if f.name in ("decision_latest.json", "sample_decision.json", "sample_decision_rich.json"):
                continue
            try:
                stat = f.stat()
                rows.append({
                    "Filename": f.name,
                    "Size": f"{stat.st_size / 1024:.1f} KB",
                    "Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except OSError:
                continue
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No historical snapshots found")
    else:
        st.info("No historical snapshots found")


def render_settings_page(dark: bool) -> None:
    """Render the settings page."""
    st.markdown("## ⚙️ Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Display")
        st.checkbox("Dark Mode", value=dark, disabled=True, help="Use the toggle in the header")
        st.checkbox("Show Tooltips", value=True)
        st.checkbox("Auto-refresh", value=False)
    
    with col2:
        st.markdown("### Data")
        st.text_input("Output Directory", value="out/", disabled=True)
        st.number_input("Refresh Interval (sec)", value=30, min_value=10, max_value=300)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the premium dashboard."""
    st.set_page_config(
        page_title="ChakraOps Dashboard",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize session state
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"
    if "selected_snapshot" not in st.session_state:
        st.session_state.selected_snapshot = None
    if "loaded_file" not in st.session_state:
        st.session_state.loaded_file = None
    
    # Get available snapshot files
    available_files = get_available_snapshots()
    if not available_files:
        available_files = ["No files available"]
    
    # Load data based on selected snapshot or auto-detect
    data, is_sample, loaded_file = load_decision_data(st.session_state.selected_snapshot)
    st.session_state.loaded_file = loaded_file
    parsed = parse_snapshot(data)
    
    # Inject CSS first
    inject_premium_css(st.session_state.dark_mode)
    
    # Render top header and get control states
    new_dark_mode, new_file, refresh_clicked = render_top_header(
        is_sample, 
        st.session_state.dark_mode, 
        loaded_file,
        available_files
    )
    
    # Render sidebar and get current page
    selected_page = render_sidebar(st.session_state.current_page)
    
    # Handle state changes
    needs_rerun = False
    
    if selected_page != st.session_state.current_page:
        st.session_state.current_page = selected_page
        needs_rerun = True
    
    if new_dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = new_dark_mode
        needs_rerun = True
    
    if new_file:
        st.session_state.selected_snapshot = new_file
        needs_rerun = True
    
    if refresh_clicked:
        # Force reload by clearing cache-like behavior
        st.session_state.selected_snapshot = st.session_state.selected_snapshot  # Keep same file
        needs_rerun = True
    
    if needs_rerun:
        st.rerun()
    
    # Render current page
    if st.session_state.current_page == "dashboard":
        render_dashboard_page(data, parsed, is_sample, st.session_state.dark_mode, loaded_file)
    elif st.session_state.current_page == "strategies":
        render_strategies_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "analytics":
        render_analytics_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "history":
        render_history_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "settings":
        render_settings_page(st.session_state.dark_mode)
    
    # Render footer
    render_footer()


if __name__ == "__main__":
    main()
