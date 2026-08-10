/**
 * R41/R56 — Canonical routes for product contract + screenshot pack.
 * Keep in sync with App.tsx + Sidebar.tsx.
 * /positions redirects to /portfolio?tab=holdings (not primary nav).
 */
export const CANONICAL_ROUTES: Array<{
  path: string;
  name: string;
  pageTestId?: string;
  navGroup: string;
  primaryNav?: boolean;
  redirectOf?: string;
}> = [
  { path: "/", name: "Command Center", pageTestId: "page-command-center", navGroup: "Command Center", primaryNav: true },
  { path: "/today", name: "Today checklist", navGroup: "Command Center", primaryNav: true },
  { path: "/ticket", name: "Trade Ticket", navGroup: "Command Center", primaryNav: true },
  { path: "/opportunities", name: "Opportunities", pageTestId: "opportunities-page", navGroup: "Opportunities", primaryNav: true },
  { path: "/portfolio", name: "Portfolio", pageTestId: "page-portfolio", navGroup: "Portfolio", primaryNav: true },
  { path: "/journal", name: "Journal", navGroup: "Portfolio", primaryNav: true },
  {
    path: "/positions",
    name: "Positions (redirect)",
    pageTestId: "page-portfolio",
    navGroup: "Portfolio",
    primaryNav: false,
    redirectOf: "/portfolio?tab=holdings",
  },
  { path: "/universe", name: "Universe", pageTestId: "page-universe", navGroup: "Research", primaryNav: true },
  { path: "/symbol-diagnostics", name: "Symbol Diagnostics", navGroup: "Research", primaryNav: true },
  { path: "/backtest", name: "Backtest / Strategy Lab", navGroup: "Strategy Lab", primaryNav: true },
  { path: "/learn", name: "Learn", navGroup: "Strategy Lab", primaryNav: true },
  { path: "/system", name: "System Diagnostics", navGroup: "Operations", primaryNav: true },
  { path: "/notifications", name: "Notifications", pageTestId: "page-notifications", navGroup: "Operations", primaryNav: true },
  { path: "/universe-admin", name: "Universe Admin", pageTestId: "page-universe-admin", navGroup: "Operations", primaryNav: true },
  { path: "/universe-health", name: "Universe Health", pageTestId: "page-universe-health", navGroup: "Operations", primaryNav: true },
  { path: "/wheel", name: "Wheel", pageTestId: "page-wheel", navGroup: "Advanced/Legacy", primaryNav: true },
  { path: "/paper", name: "Paper", navGroup: "Advanced/Legacy", primaryNav: true },
  { path: "/reports", name: "Reports", navGroup: "Advanced/Legacy", primaryNav: true },
  { path: "/weekly", name: "Weekly Review", navGroup: "Advanced/Legacy", primaryNav: true },
];

/** R56 strategy workspace deep links (unit-tested; optional e2e). */
export const OPPORTUNITY_STRATEGY_ROUTES = [
  "/opportunities",
  "/opportunities?strategy=options",
  "/opportunities?strategy=stocks",
  "/opportunities?strategy=etf-hedge",
] as const;
export const BACKEND_URL = process.env.CHAKRAOPS_BACKEND_URL || "http://127.0.0.1:18800";
