/**
 * R41 — Canonical routes for product contract + screenshot pack.
 * Keep in sync with App.tsx.
 */
export const CANONICAL_ROUTES: Array<{
  path: string;
  name: string;
  pageTestId?: string;
  navGroup: string;
}> = [
  { path: "/", name: "Command Center", pageTestId: "page-command-center", navGroup: "Command Center" },
  { path: "/today", name: "Today checklist", navGroup: "Command Center" },
  { path: "/ticket", name: "Trade Ticket", navGroup: "Command Center" },
  { path: "/opportunities", name: "Opportunities", pageTestId: "opportunities-page", navGroup: "Opportunities" },
  { path: "/portfolio", name: "Portfolio", pageTestId: "page-portfolio", navGroup: "Portfolio" },
  { path: "/positions", name: "Positions", navGroup: "Portfolio" },
  { path: "/universe", name: "Universe", pageTestId: "page-universe", navGroup: "Research" },
  { path: "/symbol-diagnostics", name: "Symbol Diagnostics", navGroup: "Research" },
  { path: "/backtest", name: "Backtest / Strategy Lab", navGroup: "Strategy Lab" },
  { path: "/learn", name: "Learn", navGroup: "Strategy Lab" },
  { path: "/system", name: "System Diagnostics", navGroup: "Operations" },
  { path: "/universe-admin", name: "Universe Admin", pageTestId: "page-universe-admin", navGroup: "Operations" },
  { path: "/universe-health", name: "Universe Health", pageTestId: "page-universe-health", navGroup: "Operations" },
  { path: "/wheel", name: "Wheel", pageTestId: "page-wheel", navGroup: "Advanced/Legacy" },
  { path: "/paper", name: "Paper", navGroup: "Advanced/Legacy" },
  { path: "/reports", name: "Reports", navGroup: "Advanced/Legacy" },
  { path: "/weekly", name: "Weekly Review", navGroup: "Advanced/Legacy" },
  { path: "/journal", name: "Journal", navGroup: "Advanced/Legacy" },
  { path: "/notifications", name: "Notifications", pageTestId: "page-notifications", navGroup: "Advanced/Legacy" },
];

export const BACKEND_URL = process.env.CHAKRAOPS_BACKEND_URL || "http://127.0.0.1:18800";
