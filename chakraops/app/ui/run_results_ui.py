# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase UI-1: Universe Run Results and System Diagnostics UI."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import streamlit as st


def _get_latest_run_data() -> Dict[str, Any]:
    """Fetch latest run (uses same logic as API)."""
    try:
        from app.api.eval_routes import build_latest_run_response
        return build_latest_run_response()
    except Exception:
        return {}


def _get_symbol_data(symbol: str) -> Dict[str, Any]:
    """Fetch symbol drilldown (uses same logic as API)."""
    try:
        from app.api.eval_routes import build_symbol_response
        return build_symbol_response(symbol)
    except Exception:
        return {"symbol": symbol, "error": "Failed to load"}


def _get_system_health() -> Dict[str, Any]:
    """Fetch system health (uses same logic as API)."""
    try:
        from app.api.eval_routes import build_system_health_response
        return build_system_health_response()
    except Exception:
        return {}


def _fmt(v: Any, default: str = "—") -> str:
    if v is None:
        return default
    if isinstance(v, float):
        return f"{v:.2f}" if v == v else default
    return str(v)


def _fmt_currency(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


def render_run_results_tab() -> None:
    """Render Run Results tab: table, filters, summary cards, symbol drilldown."""
    data = _get_latest_run_data()
    status = data.get("status") or "NO_RUNS"
    run_id = data.get("run_id")
    as_of = data.get("as_of")
    top_ranked = data.get("top_ranked") or []
    warnings = data.get("warnings") or []

    # Summary cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Status", status)
    with col2:
        st.metric("Evaluated", data.get("symbols_evaluated", 0))
    with col3:
        st.metric("Skipped", data.get("symbols_skipped", 0))
    with col4:
        st.metric("Duration (s)", _fmt(data.get("duration_sec")))
    with col5:
        st.metric("Run ID", (run_id or "—")[:16] + "..." if run_id and len(run_id) > 16 else (run_id or "—"))

    if as_of:
        st.caption(f"As of: {as_of}")

    if warnings:
        with st.expander("⚠️ Warnings", expanded=True):
            for w in warnings:
                st.write(f"• {w}")

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        tier_filter = st.selectbox("Tier", ["All", "CORE", "SATELLITE", "PARKING"], key="rr_tier")
    with col_f2:
        status_filter = st.selectbox("Status", ["All", "eligible", "fail", "hold", "blocked"], key="rr_status")
    with col_f3:
        pass  # sector/cluster placeholder

    # Filter rows
    rows = top_ranked
    if status_filter != "All":
        sf = status_filter.lower()
        rows = [r for r in rows if (r.get("status") or "").lower() == sf or (sf == "fail" and (r.get("status") or "").lower() in ("blocked", "unknown"))]
    # Tier filter: we don't have tier in top_ranked; skip for now

    # Table
    if not rows:
        st.info("No ranked candidates. Run an evaluation to populate.")
        return

    table_data = []
    for r in rows:
        sc = r.get("strike")
        dte = r.get("dte")
        prem = r.get("premium")
        table_data.append({
            "Symbol": r.get("symbol"),
            "Status": r.get("status"),
            "Score": r.get("score"),
            "Band": r.get("band") or "—",
            "Mode": r.get("mode") or "CSP",
            "Strike": _fmt(sc),
            "DTE": _fmt(dte),
            "Premium": _fmt_currency(prem),
            "Key Advisory": (r.get("primary_reason") or "")[:60] + ("..." if len(str(r.get("primary_reason") or "")) > 60 else ""),
        })

    df = st.dataframe(table_data, use_container_width=True, hide_index=True)

    # Symbol drilldown: on row click we'd need streamlit to support it; use selectbox
    st.markdown("---")
    st.subheader("Symbol drilldown")
    symbols = [r.get("symbol") for r in rows if r.get("symbol")]
    selected = st.selectbox("Select symbol", [""] + list(dict.fromkeys(symbols)), key="rr_drilldown")
    if selected:
        sym_data = _get_symbol_data(selected)
        _render_symbol_drawer(sym_data)


def _render_symbol_drawer(sym_data: Dict[str, Any]) -> None:
    """Render symbol drilldown drawer (Stage-1, Stage-2, Guardrails, Exit Plan, Raw JSON)."""
    if sym_data.get("error"):
        st.error(sym_data["error"])
        return

    sym = sym_data.get("symbol", "?")
    st.markdown(f"**{sym}** — evaluation detail")

    # Stage-1 box
    with st.expander("Stage-1: Data sufficiency", expanded=True):
        s1 = sym_data.get("stage1") or {}
        ds = s1.get("data_sufficiency") or {}
        st.write("**Data sufficiency**")
        st.write("- Status:", ds.get("status", "—"))
        st.write("- Required missing:", ds.get("required_data_missing") or [])
        st.write("- Required stale:", ds.get("required_data_stale") or [])
        st.write("**Data as of:**", s1.get("data_as_of", "—"))
        st.write("**Endpoints used:**", s1.get("endpoints_used") or [])

    # Stage-2 box
    with st.expander("Stage-2: Eligibility", expanded=True):
        s2 = sym_data.get("stage2") or {}
        st.write("**Score:**", s2.get("score"))
        st.write("**Band:**", s2.get("band"))
        el = s2.get("eligibility") or {}
        st.write("**Eligibility status:**", el.get("status"))
        st.write("**Primary reason:**", el.get("primary_reason"))
        st.write("**Fail reasons:**", s2.get("fail_reasons") or [])

    # Guardrails box
    with st.expander("Sizing / Guardrails"):
        sizing = sym_data.get("sizing") or {}
        st.write("**Advisories:**", sizing.get("advisories") or [])

    # Exit Plan box
    with st.expander("Exit plan"):
        ep = sym_data.get("exit_plan") or {}
        st.write("T1:", ep.get("t1"), "| T2:", ep.get("t2"), "| DTE targets:", ep.get("dte_targets"), "| Priority:", ep.get("priority"))

    # Raw JSON
    with st.expander("Raw JSON"):
        st.json(sym_data)


def render_diagnostics_tab() -> None:
    """Render System Diagnostics tab: wall time, cache, budget, watchdog, run IDs."""
    health = _get_system_health()
    run_id = health.get("run_id")
    as_of = health.get("as_of")

    st.subheader("Last run diagnostics")
    st.caption(f"Run: {run_id or '—'} | As of: {as_of or '—'}")

    # Throughput (from latest-run if needed)
    try:
        from app.api.eval_routes import build_latest_run_response
        lr = build_latest_run_response()
        tp = lr.get("throughput") or {}
    except Exception:
        tp = {}

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Wall time (sec)", _fmt(tp.get("wall_time_sec")))
    with col2:
        st.metric("Requests estimated", tp.get("requests_estimated") or "—")
    with col3:
        cache = health.get("cache") or {}
        st.metric("Cache hit rate %", _fmt(cache.get("cache_hit_rate_pct")))

    st.markdown("**Cache hit rate by endpoint**")
    by_ep = cache.get("cache_hit_rate_by_endpoint") or {}
    if by_ep:
        for ep, stats in by_ep.items():
            st.write(f"- {ep}: {stats.get('hit_rate_pct', '—')}%")
    else:
        st.caption("No endpoint data")

    st.markdown("**Watchdog warnings**")
    wd = health.get("watchdog") or {}
    wd_warnings = wd.get("warnings") or []
    if wd_warnings:
        for w in wd_warnings:
            reason = w.get("reason") or w.get("failed") if isinstance(w, dict) else str(w)
            st.warning(reason)
    else:
        st.caption("None")

    budget = health.get("budget") or {}
    st.markdown("**Budget**")
    st.write("- Requests estimated:", budget.get("requests_estimated"))
    st.write("- Max estimate:", budget.get("max_requests_estimate"))
    st.write("- Budget stopped:", budget.get("budget_stopped"))
    if budget.get("budget_warning"):
        st.warning(budget["budget_warning"])

    st.markdown("**Last 10 run IDs**")
    recent = health.get("recent_run_ids") or []
    for rid in recent[:10]:
        st.code(rid)
