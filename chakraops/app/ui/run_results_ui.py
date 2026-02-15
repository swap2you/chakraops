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


def _render_export_run_button() -> None:
    """Download latest run JSON from artifacts or evaluation store."""
    try:
        import json
        from dataclasses import asdict
        from app.core.eval.run_artifacts import get_latest_run_dir
        from app.core.eval.evaluation_store import load_latest_pointer, load_run
        data = None
        run_dir = get_latest_run_dir()
        if run_dir:
            p = run_dir / "evaluation.json"
            if p.exists():
                data = p.read_text(encoding="utf-8")
        if not data:
            pointer = load_latest_pointer()
            if pointer:
                run = load_run(pointer.run_id)
                if run:
                    data = json.dumps(asdict(run), indent=2, default=str)
        if data:
            st.download_button("📥 Download latest run JSON", data=data, file_name="latest_run.json", mime="application/json", key="rr_dl_run")
        else:
            st.caption("No run available")
    except Exception:
        st.caption("Export unavailable")


def _render_export_diagnostics_button() -> None:
    """Download latest diagnostics JSON."""
    try:
        import json
        from app.core.eval.run_diagnostics_store import load_run_diagnostics
        diag = load_run_diagnostics()
        if diag:
            data = json.dumps(diag, indent=2, default=str)
            st.download_button("📥 Download diagnostics JSON", data=data, file_name="latest_diagnostics.json", mime="application/json", key="rr_dl_diag")
        else:
            st.caption("No diagnostics")
    except Exception:
        st.caption("Export unavailable")


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
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        tier_filter = st.selectbox("Tier", ["All", "CORE", "SATELLITE", "PARKING"], key="rr_tier")
    with col_f2:
        band_filter = st.selectbox("Band", ["All", "A", "B", "C"], key="rr_band")
    with col_f3:
        status_filter = st.selectbox("Verdict/Status", ["All", "ELIGIBLE", "HOLD", "BLOCKED", "FAIL"], key="rr_status")
    with col_f4:
        cluster_filter = st.selectbox("Cluster risk", ["All", "LOW", "MED", "HIGH"], key="rr_cluster")

    # Filter rows (use normalized keys: final_verdict, score, expiration)
    rows = top_ranked
    if status_filter != "All":
        sf = status_filter.upper()
        rows = [r for r in rows if (r.get("final_verdict") or r.get("status") or "").upper() == sf or (
            sf == "FAIL" and (r.get("final_verdict") or r.get("status") or "").upper() in ("BLOCKED", "UNKNOWN")
        )]
    if band_filter != "All":
        rows = [r for r in rows if (r.get("band") or "").upper() == band_filter]
    # Tier and cluster: not in top_ranked by default; pass-through if present
    if tier_filter != "All":
        rows = [r for r in rows if (r.get("tier") or "").upper() == tier_filter]
    if cluster_filter != "All":
        rows = [r for r in rows if (r.get("cluster_risk") or r.get("cluster") or "").upper() == cluster_filter]

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
            "Status": r.get("final_verdict") or r.get("status"),
            "Score": r.get("score"),
            "Band": r.get("band") or "—",
            "Mode": r.get("mode") or "CSP",
            "Strike": _fmt(sc),
            "DTE": _fmt(dte),
            "Premium": _fmt_currency(prem),
            "Key Advisory": (r.get("primary_reason") or "")[:60] + ("..." if len(str(r.get("primary_reason") or "")) > 60 else ""),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # Exports (use same process; no HTTP)
    col_ex1, col_ex2, _ = st.columns([1, 1, 2])
    with col_ex1:
        _render_export_run_button()
    with col_ex2:
        _render_export_diagnostics_button()

    # Symbol drilldown: on row click we'd need streamlit to support it; use selectbox
    st.markdown("---")
    st.subheader("Symbol drilldown")
    symbols = [r.get("symbol") for r in rows if r.get("symbol")]
    selected = st.selectbox("Select symbol", [""] + list(dict.fromkeys(symbols)), key="rr_drilldown")
    if selected:
        sym_data = _get_symbol_data(selected)
        _render_symbol_drawer(sym_data)


def _render_symbol_drawer(sym_data: Dict[str, Any]) -> None:
    """Render symbol drilldown: Stage-1 → Stage-2 → Sizing (base→guardrail) → Exit Plan → Traces → Raw JSON."""
    if sym_data.get("error"):
        st.error(sym_data["error"])
        return

    sym = sym_data.get("symbol", "?")
    st.markdown(f"**{sym}** — evaluation detail")

    # 1. Stage-1: Data sufficiency
    with st.expander("Stage-1: Data sufficiency", expanded=True):
        s1 = sym_data.get("stage1") or {}
        ds = s1.get("data_sufficiency") or {}
        st.write("**Data sufficiency**")
        st.write("- Status:", ds.get("status", "—"))
        st.write("- Required missing:", ds.get("required_data_missing") or [])
        st.write("- Required stale:", ds.get("required_data_stale") or [])
        st.write("**Data as of:**", s1.get("data_as_of", "—"))
        st.write("**Endpoints used:**", s1.get("endpoints_used") or [])

    # 2. Stage-2: Eligibility (score, band, contract)
    with st.expander("Stage-2: Eligibility", expanded=True):
        s2 = sym_data.get("stage2") or {}
        st.write("**Score:**", s2.get("score"), "| **Band:**", s2.get("band"))
        el = s2.get("eligibility") or {}
        st.write("**Eligibility status:**", el.get("status"))
        st.write("**Primary reason:**", el.get("primary_reason"))
        st.write("**Fail reasons:**", s2.get("fail_reasons") or [])
        sc = s2.get("selected_contract") or s2.get("candidate_contract") or {}
        if sc:
            st.write("**Selected contract:**", f"strike={sc.get('strike')} dte={sc.get('dte')} delta={sc.get('delta')}")

    # 3. Sizing: baseline → guardrail
    with st.expander("Sizing (base→guardrail)", expanded=False):
        sizing = sym_data.get("sizing") or {}
        st.write("**Baseline contracts:**", sizing.get("baseline_contracts", "—"))
        st.write("**Guardrail adjusted:**", sizing.get("guardrail_adjusted_contracts", "—"))
        st.write("**Advisories:**", sizing.get("advisories") or [])

    # 4. Exit Plan
    with st.expander("Exit plan", expanded=False):
        ep = sym_data.get("exit_plan") or {}
        st.write("T1:", ep.get("t1"), "| T2:", ep.get("t2"), "| DTE targets:", ep.get("dte_targets"), "| Priority:", ep.get("priority"))

    # 5. Traces
    with st.expander("Traces", expanded=False):
        traces = sym_data.get("traces") or {}
        st.json(traces)

    # 6. Raw JSON
    with st.expander("Raw JSON", expanded=False):
        st.json(sym_data)


def render_diagnostics_tab() -> None:
    """Render System Diagnostics tab: Recent Runs table, cache, budget, watchdog."""
    # Recent Runs table
    st.subheader("Recent Runs")
    try:
        from app.api.eval_routes import build_runs_response
        runs = build_runs_response(limit=10)
        if runs:
            rows = [
                {
                    "Run ID": r.get("run_id", "")[:24] + "..." if r.get("run_id") and len(r.get("run_id", "")) > 24 else (r.get("run_id") or "—"),
                    "As of": str(r.get("as_of", "—"))[:19] if r.get("as_of") else "—",
                    "Status": r.get("status", "—"),
                    "Duration (s)": _fmt(r.get("duration_sec")),
                    "Evaluated": r.get("symbols_evaluated", 0),
                    "Eligible": r.get("eligible_count", 0),
                    "Warnings": r.get("warnings_count", 0),
                }
                for r in runs
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No runs found")
    except Exception as e:
        st.caption(f"Runs unavailable: {e}")

    st.markdown("---")
    st.subheader("Last run diagnostics")
    health = _get_system_health()
    run_id = health.get("run_id")
    as_of = health.get("as_of")
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
