"""
ChakraOps UI design system — premium SaaS admin aesthetic.

Design tokens and reusable components for layout, typography, cards, badges.
UI-only; no execution logic, gates, or data model changes.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens (Stripe/GitHub-ish: calm, spacious, high contrast for status)
# ---------------------------------------------------------------------------

# Colors
COLORS = {
    "bg": "#f6f8fa",
    "card_bg": "#ffffff",
    "border": "#d0d7de",
    "border_light": "#eaeef2",
    "text_primary": "#1f2328",
    "text_muted": "#656d76",
    "accent": "#0969da",
    "success": "#1a7f37",
    "warning": "#9a6700",
    "danger": "#cf222e",
    "nav_bg": "#1f2328",
    "nav_text": "#e6edf3",
    "nav_text_muted": "#8b949e",
}

# Spacing scale (px)
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
}

# Border radii
RADII = {
    "sm": 6,
    "md": 10,
    "lg": 14,
}

# Shadows
SHADOWS = {
    "subtle_1": "0 1px 2px rgba(31, 35, 40, 0.04)",
    "subtle_2": "0 1px 3px rgba(31, 35, 40, 0.08)",
}

# Typography sizes (rem) — headings dominant over content
TYPO = {
    "h1": "1.25rem",
    "h2": "1.1rem",
    "h3": "1rem",
    "body": "0.875rem",
    "small": "0.8rem",
}

# Status → tone for badges (BLOCKED=danger, ALLOWED=success, REVIEW/DEGRADED=warning)
STATUS_TONE = {
    "BLOCKED": "danger",
    "ALLOWED": "success",
    "REVIEW": "warning",
    "DEGRADED": "warning",
    "PASS": "success",
    "FAIL": "danger",
}


def _tone_color(tone: Optional[str]) -> str:
    if not tone:
        return COLORS["text_primary"]
    t = (tone or "").lower()
    if t in ("success", "green"):
        return COLORS["success"]
    if t in ("danger", "error", "red"):
        return COLORS["danger"]
    if t in ("warning", "warn", "amber", "yellow"):
        return COLORS["warning"]
    return COLORS["text_primary"]


def inject_global_css() -> None:
    """
    Inject global CSS for premium SaaS admin look.
    - Page background, max-width container, system font stack
    - Compact buttons, tabs, expanders, tables
    - Card and badge styles; status colors; footer
    """
    s = SPACING
    r = RADII
    sh = SHADOWS
    c = COLORS
    t = TYPO
    font_stack = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    st.markdown(
        f"""
        <style>
        /* Base */
        .stApp {{ background: {c['bg']}; }}
        .main .block-container {{ max-width: 1320px; padding: {s['lg']}px {s['xl']}px; margin: 0 auto; }}
        * {{ font-family: {font_stack}; }}

        /* Reduce default block padding */
        .main .block-container > div {{ padding-top: {s['sm']}px; }}
        [data-testid="stVerticalBlock"] > div {{ padding-top: {s['xs']}px; }}

        /* Header / nav */
        [data-testid="stHeader"] {{ background: {c['nav_bg']}; }}
        header[data-testid="stHeader"] {{ border-bottom: 1px solid {c['border']}; }}

        /* Buttons: compact */
        .stButton > button {{ border-radius: {r['sm']}px; padding: {s['sm']}px {s['lg']}px; font-size: {t['body']}; }}

        /* Tabs: clean */
        .stTabs [data-baseweb="tab-list"] {{ gap: {s['xs']}px; }}
        .stTabs [data-baseweb="tab"] {{ padding: {s['sm']}px {s['lg']}px; font-size: {t['body']}; }}

        /* Expanders: accordion-like, no heavy borders */
        .streamlit-expanderHeader {{ background: {c['card_bg']}; border: 1px solid {c['border_light']}; border-radius: {r['sm']}px; }}
        .streamlit-expanderContent {{ border: 1px solid {c['border_light']}; border-top: none; border-radius: 0 0 {r['sm']}px {r['sm']}px; }}

        /* DataFrames: compact, striped */
        .stDataFrame {{ font-size: {t['small']}; }}
        .stDataFrame td, .stDataFrame th {{ padding: {s['xs']}px {s['sm']}px !important; }}
        div[data-testid="stDataFrameResizable"] {{ border-radius: {r['sm']}px; border: 1px solid {c['border_light']}; overflow: hidden; }}
        .stDataFrame tbody tr:nth-child(even) {{ background: {c['bg']}; }}

        /* Metrics: compact */
        [data-testid="stMetric"] {{ padding: {s['sm']}px; }}
        [data-testid="stMetricValue"] {{ font-size: 1rem; }}

        /* Cards (theme class) */
        .chakra-theme-card {{ background: {c['card_bg']}; border: 1px solid {c['border_light']}; border-radius: {r['md']}px;
            padding: {s['lg']}px; margin-bottom: {s['lg']}px; box-shadow: {sh['subtle_1']}; }}
        .chakra-theme-card h4 {{ margin: 0 0 {s['sm']}px 0; font-size: {t['h3']}; font-weight: 600; color: {c['text_primary']}; }}
        .chakra-theme-card-header-only {{ margin-bottom: {s['sm']}px; }}
        .chakra-theme-hero {{ border-left: 4px solid {c['border']}; }}
        .chakra-theme-hero.hero-blocked {{ border-left-color: {c['danger']}; }}
        .chakra-theme-hero.hero-allowed {{ border-left-color: {c['success']}; }}
        .chakra-theme-hero.hero-warning {{ border-left-color: {c['warning']}; }}

        /* Badges */
        .chakra-theme-badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 600; font-size: {t['small']}; letter-spacing: 0.02em; }}

        /* Footer */
        .chakra-theme-footer {{ margin-top: {s['2xl']}px; padding: {s['lg']}px; border-top: 1px solid {c['border_light']};
            color: {c['text_muted']}; font-size: {t['small']}; text-align: center; }}

        /* Live pulse */
        .chakra-theme-pulse {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; vertical-align: middle;
            animation: chakra-pulse 2s infinite; }}
        @keyframes chakra-pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}

        /* Sidebar: narrower */
        [data-testid="stSidebar"] {{ min-width: 220px; }}
        [data-testid="stSidebar"] .stMarkdown {{ font-size: {t['body']}; }}

        /* Hide Streamlit branding (optional, keep if policy requires) */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def icon_svg(name: str, size: int = 16, color: str = "currentColor") -> str:
    """Return inline SVG for named icon. name: circle-live, shield, database, pulse, alert."""
    color = color or "currentColor"
    # Minimal 16px icons as data-uri style inline SVGs (simplified for Streamlit markdown)
    icons = {
        "circle-live": f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="4" fill="{color}" opacity="0.9"/><circle cx="8" cy="8" r="6" stroke="{color}" stroke-width="1.5" fill="none" opacity="0.6"/></svg>',
        "shield": f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="{color}" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg"><path d="M8 2L2 4v4c0 3.5 2.5 6 6 8 3.5-2 6-4.5 6-8V4L8 2z"/></svg>',
        "database": f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="{color}" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>',
        "pulse": f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="{color}" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg"><path d="M2 8h2l2-4 2 8 2-4h2"/></svg>',
        "alert": f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="{color}" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg"><path d="M8 3v5M8 11v1M2 14h12a1 1 0 001-1V3a1 1 0 00-1-1H2a1 1 0 00-1 1v10a1 1 0 001 1z"/></svg>',
    }
    svg = icons.get(name, icons["circle-live"])
    return f'<span style="display:inline-block;vertical-align:middle;">{svg}</span>'


def badge(text: str, tone: Optional[str] = None) -> str:
    """Return HTML for a small badge. tone: success, danger, warning, or None (neutral)."""
    tone = (tone or "").lower()
    bg = _tone_color(tone) if tone else COLORS["border"]
    # Light background with colored text for readability
    if tone == "success":
        bg_style = f"background: {COLORS['success']}; color: white;"
    elif tone == "danger":
        bg_style = f"background: {COLORS['danger']}; color: white;"
    elif tone == "warning":
        bg_style = f"background: {COLORS['warning']}; color: white;"
    else:
        bg_style = f"background: {COLORS['border_light']}; color: {COLORS['text_primary']};"
    return f'<span class="chakra-theme-badge" style="{bg_style}">{text}</span>'


def metric_tile(
    label: str,
    value: Any,
    delta: Optional[str] = None,
    tone: Optional[str] = None,
) -> None:
    """Render a compact metric (label + value, optional delta with tone)."""
    delta_html = ""
    if delta is not None:
        c = _tone_color(tone) if tone else COLORS["text_muted"]
        delta_html = f' <span style="font-size:{TYPO["small"]};color:{c};">{delta}</span>'
    st.markdown(
        f'<div style="margin-bottom:{SPACING["sm"]}px;"><span style="font-size:{TYPO["small"]};color:{COLORS["text_muted"]};">{label}</span><br/>'
        f'<span style="font-size:1rem;font-weight:600;color:{COLORS["text_primary"]};">{value}</span>{delta_html}</div>',
        unsafe_allow_html=True,
    )


def section_header(
    title: str,
    subtitle: Optional[str] = None,
    right_slot: Optional[str] = None,
) -> None:
    """Render a section header (title, optional subtitle, optional right-side HTML)."""
    sub = f'<p style="margin:0;font-size:{TYPO["small"]};color:{COLORS["text_muted"]};">{subtitle}</p>' if subtitle else ""
    right = f'<div style="float:right;">{right_slot}</div>' if right_slot else ""
    st.markdown(
        f'<div style="margin-bottom:{SPACING["md"]}px;">{right}'
        f'<h3 style="margin:0 0 4px 0;font-size:{TYPO["h2"]};font-weight:600;color:{COLORS["text_primary"]};">{title}</h3>{sub}</div>',
        unsafe_allow_html=True,
    )


def card(
    title: str,
    body_fn: Callable[[], None],
    icon: Optional[str] = None,
    status_badge: Optional[str] = None,
    hero_tone: Optional[str] = None,
) -> None:
    """
    Render a card: header bar (title, optional icon/badge), then body via body_fn.
    Body content appears below the header; use card_html when body is static HTML.
    hero_tone: 'blocked' | 'allowed' | 'warning' for left border accent.
    """
    card_header(title, icon=icon, status_badge=status_badge, hero_tone=hero_tone)
    with st.container():
        body_fn()


def card_header(
    title: str,
    icon: Optional[str] = None,
    status_badge: Optional[str] = None,
    hero_tone: Optional[str] = None,
) -> None:
    """Render only the card header bar; caller renders content below."""
    icon_html = ""
    if icon:
        icon_html = icon_svg(icon, size=18, color=COLORS["text_muted"]) + " "
    badge_html = ""
    if status_badge:
        tone = STATUS_TONE.get(status_badge.upper(), "")
        badge_html = " " + badge(status_badge, tone)
    hero_class = ""
    if hero_tone:
        hero_class = f" chakra-theme-hero hero-{hero_tone}"
    st.markdown(
        f'<div class="chakra-theme-card chakra-theme-card-header-only{hero_class}">'
        f'<h4>{icon_html}{title}{badge_html}</h4></div>',
        unsafe_allow_html=True,
    )


def card_html(title: str, body_html: str, icon: Optional[str] = None, status_badge: Optional[str] = None, hero_tone: Optional[str] = None) -> None:
    """Render a card with static HTML body (no callback). Use when body is simple HTML."""
    icon_html = ""
    if icon:
        icon_html = icon_svg(icon, size=18, color=COLORS["text_muted"]) + " "
    badge_html = ""
    if status_badge:
        tone = STATUS_TONE.get(status_badge.upper(), "")
        badge_html = " " + badge(status_badge, tone)
    hero_class = ""
    if hero_tone:
        hero_class = f" chakra-theme-hero hero-{hero_tone}"
    st.markdown(
        f'<div class="chakra-theme-card{hero_class}">'
        f'<h4>{icon_html}{title}{badge_html}</h4>'
        f'{body_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def humanize_label(key: str) -> str:
    """Convert snake_case or camelCase to Title Case human label."""
    if not key:
        return key
    s = str(key).replace("_", " ").replace("-", " ")
    return " ".join(w.capitalize() for w in s.split())
