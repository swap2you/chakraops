import { useState, useEffect } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Globe,
  Search,
  Activity,
  PieChart,
  Bell,
  RotateCcw,
  BookOpen,
  BarChart3,
  FileText,
  Settings,
  Heart,
  Calendar,
  CalendarCheck,
  LineChart,
  GraduationCap,
  Ticket,
  Target,
} from "lucide-react";
import { getWheelPageMode, isWheelLinkVisible, getShowAdvanced, setShowAdvanced } from "@/config/features";

/** R39/R56: Command Center IA — compact product groups (strategy workspaces live under Opportunities). */
const GROUP_ORDER = [
  "Command Center",
  "Opportunities",
  "Portfolio",
  "Research",
  "Strategy Lab",
  "Operations",
  "Advanced/Legacy",
] as const;

type NavGroup = (typeof GROUP_ORDER)[number];

const navBase: Array<{
  path: string;
  label: string;
  icon: typeof LayoutDashboard;
  group: NavGroup;
  wheel?: boolean;
  legacyNote?: boolean;
}> = [
  { path: "/", label: "Command Center", icon: LayoutDashboard, group: "Command Center" },
  { path: "/today", label: "Today checklist", icon: Calendar, group: "Command Center" },
  { path: "/ticket", label: "Trade Ticket", icon: Ticket, group: "Command Center" },
  { path: "/opportunities", label: "Opportunities", icon: Target, group: "Opportunities" },
  { path: "/portfolio", label: "Portfolio", icon: PieChart, group: "Portfolio" },
  { path: "/journal", label: "Journal", icon: BookOpen, group: "Portfolio" },
  { path: "/universe", label: "Universe", icon: Globe, group: "Research" },
  { path: "/symbol-diagnostics", label: "Symbol Diagnostics", icon: Search, group: "Research" },
  { path: "/backtest", label: "Strategy Lab", icon: LineChart, group: "Strategy Lab" },
  { path: "/strategy-builder", label: "Strategy Builder", icon: Target, group: "Strategy Lab" },
  { path: "/learn", label: "Learn", icon: GraduationCap, group: "Strategy Lab" },
  { path: "/system", label: "System Diagnostics", icon: Activity, group: "Operations" },
  { path: "/notifications", label: "Notifications", icon: Bell, group: "Operations" },
  // R70-DEF-081: demote secondary Universe ops into Advanced to reduce nav clutter
  { path: "/universe-admin", label: "Universe Admin", icon: Settings, group: "Advanced/Legacy", legacyNote: true },
  { path: "/universe-health", label: "Universe Health", icon: Heart, group: "Advanced/Legacy", legacyNote: true },
  { path: "/wheel", label: "Wheel", icon: RotateCcw, wheel: true, group: "Advanced/Legacy", legacyNote: true },
  { path: "/paper", label: "Paper", icon: FileText, group: "Advanced/Legacy", legacyNote: true },
  { path: "/reports", label: "Reports", icon: BarChart3, group: "Advanced/Legacy", legacyNote: true },
  { path: "/weekly", label: "Weekly Review", icon: CalendarCheck, group: "Advanced/Legacy", legacyNote: true },
];

function groupTestId(group: string): string {
  return `nav-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+$/g, "")}`;
}

export function Sidebar() {
  const wheelMode = getWheelPageMode();
  const [showAdvanced, setShowAdvancedState] = useState(getShowAdvanced());
  const wheelVisible = isWheelLinkVisible();

  useEffect(() => {
    setShowAdvancedState(getShowAdvanced());
  }, [wheelVisible]);

  const nav = navBase
    .filter((item) => {
      if (!item.wheel) return true;
      return wheelVisible;
    })
    .map((item) => {
      if (item.wheel && wheelMode === "admin") {
        return { ...item, label: "Wheel (Admin)" };
      }
      return item;
    });

  return (
    <aside className="glass flex w-56 shrink-0 flex-col border-r border-zinc-200/80 dark:border-zinc-800/80">
      <div className="flex h-14 items-center gap-2.5 border-b border-zinc-200/80 px-4 dark:border-zinc-800/80">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 text-sm font-bold text-emerald-950 shadow-glow-emerald"
          aria-hidden
        >
          C
        </span>
        <span className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          ChakraOps
        </span>
      </div>
      <nav className="flex-1 space-y-3 overflow-y-auto px-2.5 py-3">
        {GROUP_ORDER.map((group) => {
          const items = nav.filter((item) => item.group === group);
          if (items.length === 0) return null;
          const isLegacy = group === "Advanced/Legacy";
          return (
            <div key={group} className="space-y-0.5" data-testid={groupTestId(group)}>
              <div className="px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-400 dark:text-zinc-600">
                {isLegacy ? "Advanced" : group}
              </div>
              {isLegacy && (
                <p className="px-2.5 pb-1 text-[10px] leading-snug text-zinc-400 dark:text-zinc-600" data-testid="nav-legacy-note">
                  Recovery / admin only — not daily decision surfaces
                </p>
              )}
              {items.map(({ path, label, icon: Icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-150 ease-out ${
                      isActive
                        ? "bg-emerald-500/10 text-emerald-700 shadow-[inset_2px_0_0_0_rgb(16_185_129)] dark:bg-emerald-400/10 dark:text-emerald-300"
                        : "text-zinc-600 hover:translate-x-0.5 hover:bg-zinc-100/80 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/60 dark:hover:text-zinc-100"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={`h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110 ${
                          isActive ? "text-emerald-600 dark:text-emerald-400" : ""
                        }`}
                      />
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          );
        })}
        {wheelMode === "advanced" && (
          <div className="mt-2 border-t border-zinc-200/80 px-2.5 py-2.5 dark:border-zinc-800/80">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-500 transition-colors hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
              <input
                type="checkbox"
                checked={showAdvanced}
                onChange={(e) => {
                  const v = e.target.checked;
                  setShowAdvanced(v);
                  setShowAdvancedState(v);
                }}
                className="rounded border-zinc-300 accent-emerald-500 dark:border-zinc-600"
              />
              Show advanced
            </label>
          </div>
        )}
      </nav>
    </aside>
  );
}
