#!/usr/bin/env python3
"""R41 — Generate screen/control inventories from frontend sources."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
OUT = ROOT / "docs" / "ai" / "releases" / "R41"
OUT.mkdir(parents=True, exist_ok=True)

ROUTES = [
    {"path": "/", "component": "DashboardPage.tsx", "label": "Command Center", "nav_group": "Command Center"},
    {"path": "/today", "component": "TodayPage.tsx", "label": "Today checklist", "nav_group": "Command Center"},
    {"path": "/ticket", "component": "TradeTicketPage.tsx", "label": "Trade Ticket", "nav_group": "Command Center"},
    {"path": "/opportunities", "component": "OpportunitiesPage.tsx", "label": "Opportunities", "nav_group": "Opportunities"},
    {"path": "/portfolio", "component": "PortfolioPage.tsx", "label": "Portfolio", "nav_group": "Portfolio"},
    {"path": "/positions", "component": "PositionsPage.tsx", "label": "Positions", "nav_group": "Portfolio"},
    {"path": "/universe", "component": "UniversePage.tsx", "label": "Universe", "nav_group": "Research"},
    {"path": "/symbol-diagnostics", "component": "SymbolDiagnosticsPage.tsx", "label": "Symbol Diagnostics", "nav_group": "Research"},
    {"path": "/backtest", "component": "BacktestPage.tsx", "label": "Backtest", "nav_group": "Strategy Lab"},
    {"path": "/learn", "component": "LearnPage.tsx", "label": "Learn", "nav_group": "Strategy Lab"},
    {"path": "/system", "component": "SystemDiagnosticsPage.tsx", "label": "System Diagnostics", "nav_group": "Operations"},
    {"path": "/universe-admin", "component": "UniverseAdminPage.tsx", "label": "Universe Admin", "nav_group": "Operations"},
    {"path": "/universe-health", "component": "UniverseHealthPage.tsx", "label": "Universe Health", "nav_group": "Operations"},
    {"path": "/wheel", "component": "WheelPage.tsx", "label": "Wheel", "nav_group": "Advanced/Legacy", "conditional": "VITE_WHEEL_PAGE_MODE"},
    {"path": "/paper", "component": "PaperPage.tsx", "label": "Paper", "nav_group": "Advanced/Legacy"},
    {"path": "/reports", "component": "ReportsPage.tsx", "label": "Reports", "nav_group": "Advanced/Legacy"},
    {"path": "/weekly", "component": "WeeklyReviewPage.tsx", "label": "Weekly Review", "nav_group": "Advanced/Legacy"},
    {"path": "/journal", "component": "JournalPage.tsx", "label": "Journal", "nav_group": "Advanced/Legacy"},
    {"path": "/notifications", "component": "NotificationsPage.tsx", "label": "Notifications", "nav_group": "Advanced/Legacy"},
]

TESTID_RE = re.compile(r'data-testid=["\'`]([^"\'`]+)["\'`]')
TESTID_DYN_RE = re.compile(r"data-testid=\{`([^`]+)`\}")


def classify_control(testid: str, label_hint: str = "") -> str:
    t = testid.lower()
    if any(x in t for x in ("delete", "remove", "destroy", "wipe", "repair", "force-eval", "apply")):
        return "MUTATION_PERSISTENT"
    if any(x in t for x in ("save", "ack", "archive", "propose", "add", "edit", "close", "open-ticket")):
        return "MUTATION_REVERSIBLE"
    if any(x in t for x in ("refresh", "reload", "run-eval", "backtest-run", "r40-run")):
        return "SAFE_REFRESH"
    if any(x in t for x in ("nav-", "link", "theme", "expand", "collapse", "details", "filter", "sort", "tab")):
        return "SAFE_READ"
    if "broker" in t or "place-order" in t or "send-order" in t:
        return "DISABLED_BY_POLICY"
    return "SAFE_READ"


def scan_testids() -> list[dict]:
    rows: list[dict] = []
    for path in FRONTEND.rglob("*.tsx"):
        if "test.tsx" in path.name or "_quarantine" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(FRONTEND)).replace("\\", "/")
        route_guess = ""
        for r in ROUTES:
            if r["component"] in rel:
                route_guess = r["path"]
                break
        for m in TESTID_RE.finditer(text):
            tid = m.group(1)
            rows.append(
                {
                    "route": route_guess or "(shared)",
                    "control_id": tid,
                    "label": tid,
                    "classification": classify_control(tid),
                    "source_file": rel,
                    "expected_effect": "see component",
                    "endpoint": "",
                    "mutation_persistence": "n/a" if classify_control(tid).startswith("SAFE") else "component-defined",
                    "safety_constraint": "manual_only; no broker write",
                    "test_status": "playwright_route_pack" if route_guess else "unit_or_pending",
                    "screenshot": f"out/verification/R41/screenshots/{'home' if route_guess == '/' else route_guess.strip('/').replace('/', '_')}.png"
                    if route_guess
                    else "",
                }
            )
        for m in TESTID_DYN_RE.finditer(text):
            tid = m.group(1)
            rows.append(
                {
                    "route": route_guess or "(shared)",
                    "control_id": tid,
                    "label": tid,
                    "classification": classify_control(tid),
                    "source_file": rel,
                    "expected_effect": "dynamic row/control",
                    "endpoint": "",
                    "mutation_persistence": "component-defined",
                    "safety_constraint": "manual_only; no broker write",
                    "test_status": "playwright_route_pack" if route_guess else "unit_or_pending",
                    "screenshot": "",
                }
            )
    # de-dupe by route+control_id
    seen = set()
    uniq = []
    for r in rows:
        k = (r["route"], r["control_id"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def main() -> None:
    inventory = {
        "release": "R41",
        "route_count": len(ROUTES),
        "routes": ROUTES,
        "orphans": [
            {"module": "components/CommandPalette.tsx", "status": "REMOVED_R51", "action": "deleted orphan"},
            {"module": "components/CommandBar.tsx", "status": "REMOVED_R51", "action": "deleted orphan"},
            {"module": "pages/_quarantine/*", "status": "NOT_ROUTED", "action": "KEEP_QUARANTINED"},
        ],
        "redirects": [
            {"from": "*", "to": "/"},
            {"from": "/wheel", "to": "/", "when": "VITE_WHEEL_PAGE_MODE=hidden"},
        ],
        "live_financial_surfaces": [
            {"surface": "Command Center / Opportunities", "mode": "LIVE API", "mock": "Dashboard MOCK artifact browser labeled forensics-only"},
            {"surface": "Portfolio cash/buying power", "mode": "manual trusted snapshot", "mock": False},
            {"surface": "Paper", "mode": "SIMULATION isolated", "mock": False},
            {"surface": "Backtest / R40 Strategy Lab", "mode": "SIMULATION", "mock": False},
            {"surface": "frontend/src/mock/scenarios", "mode": "test-only / unmounted providers", "mock": True},
        ],
    }
    (OUT / "SCREEN_INVENTORY.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    controls = scan_testids()
    fields = [
        "route",
        "control_id",
        "label",
        "classification",
        "source_file",
        "expected_effect",
        "endpoint",
        "mutation_persistence",
        "safety_constraint",
        "test_status",
        "screenshot",
    ]
    with (OUT / "CONTROL_INVENTORY.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(controls)

    lineage = [
        {
            "ui_field": "cash",
            "api_key": "cash / available_cash",
            "backend": "holdings_db.get_account_summary / wheel_v2_routes._portfolio_from_account",
            "source": "manual SQLite account balance",
            "calculation": "direct; never coerce from total_capital",
            "timestamp": "balance updated_at if present",
            "freshness": "operator-trusted snapshot",
            "missing_behavior": "null/unavailable → no CSP sizing; zero stays zero",
        },
        {
            "ui_field": "buying_power",
            "api_key": "buying_power",
            "backend": "holdings_db",
            "source": "manual SQLite",
            "calculation": "direct",
            "timestamp": "balance updated_at",
            "freshness": "operator-trusted",
            "missing_behavior": "null ≠ zero",
        },
        {
            "ui_field": "total_capital / equity",
            "api_key": "total_capital",
            "backend": "Account.total_capital / portfolio metrics",
            "source": "account policy + positions MTM",
            "calculation": "distinct from cash",
            "timestamp": "portfolio/metrics as-of",
            "freshness": "fail closed if required mark missing",
            "missing_behavior": "do not substitute for cash",
        },
        {
            "ui_field": "CSP collateral",
            "api_key": "strike * 100 * contracts",
            "backend": "wheel_v2 arbitration / decision engine",
            "source": "ORATS strike + trusted cash",
            "calculation": "strike×100 per contract",
            "timestamp": "provider quote-as-of",
            "freshness": "stale/missing → Stay in Cash / blocked",
            "missing_behavior": "no actionable sized CSP",
        },
        {
            "ui_field": "ORATS quote",
            "api_key": "quoteDate / side bid-ask",
            "backend": "orats_client.probe_orats_live / live strikes",
            "source": "ORATS /live/strikes",
            "calculation": "endpoint-aware field presence",
            "timestamp": "provider quote_date",
            "freshness": "not HTTP completion time",
            "missing_behavior": "probe FAIL / stale gate",
        },
        {
            "ui_field": "decision / opportunities",
            "api_key": "decision_latest / action_needed",
            "backend": "evaluation_store_v2 / evaluation_service_v2",
            "source": "out/decision_latest.json",
            "calculation": "canonical engine only",
            "timestamp": "evaluation_timestamp_utc",
            "freshness": "explicit eval only; no auto on read",
            "missing_behavior": "empty / Stay in Cash",
        },
        {
            "ui_field": "R40 Strategy Lab metrics",
            "api_key": "oos.metrics / simulation",
            "backend": "app.core.backtest.r40",
            "source": "fixtures (not ORATS hist/options)",
            "calculation": "walk-forward SIMULATION",
            "timestamp": "run timestamp",
            "freshness": "research only",
            "missing_behavior": "present=false; never claim hist entitlement",
        },
    ]
    with (OUT / "DATA_LINEAGE.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lineage[0].keys()))
        w.writeheader()
        w.writerows(lineage)

    print(f"Wrote {OUT / 'SCREEN_INVENTORY.json'}")
    print(f"Wrote {OUT / 'CONTROL_INVENTORY.csv'} ({len(controls)} controls)")
    print(f"Wrote {OUT / 'DATA_LINEAGE.csv'}")


if __name__ == "__main__":
    main()
