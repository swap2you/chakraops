import { useState, useEffect } from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Globe, Search, Activity, PieChart, Bell, RotateCcw, BookOpen, BarChart3, FileText, Settings, Heart, Calendar, CalendarCheck, LineChart, GraduationCap, Layers } from "lucide-react";
import { getWheelPageMode, isWheelLinkVisible, getShowAdvanced, setShowAdvanced } from "@/config/features";

// R34.0: logical navigation grouping (no cosmetic redesign). Every existing
// route is preserved; items are organized under stable section headers so the
// daily workflow is discoverable.
const GROUP_ORDER = ["Daily", "Research", "Account", "Insights", "Admin"] as const;

const navBase = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard, group: "Daily" },
  { path: "/today", label: "Today", icon: Calendar, group: "Daily" },
  { path: "/weekly", label: "Weekly Review", icon: CalendarCheck, group: "Daily" },
  { path: "/universe", label: "Universe", icon: Globe, group: "Research" },
  { path: "/symbol-diagnostics", label: "Symbol", icon: Search, group: "Research" },
  { path: "/wheel", label: "Wheel", icon: RotateCcw, wheel: true, group: "Research" },
  { path: "/portfolio", label: "Account & Portfolio", icon: PieChart, group: "Account" },
  { path: "/positions", label: "Positions", icon: Layers, group: "Account" },
  { path: "/journal", label: "Journal", icon: BookOpen, group: "Account" },
  { path: "/paper", label: "Paper", icon: FileText, group: "Account" },
  { path: "/notifications", label: "Notifications", icon: Bell, group: "Insights" },
  { path: "/reports", label: "Reports", icon: BarChart3, group: "Insights" },
  { path: "/backtest", label: "Backtest", icon: LineChart, group: "Insights" },
  { path: "/learn", label: "Learn", icon: GraduationCap, group: "Insights" },
  { path: "/universe-admin", label: "Universe Admin", icon: Settings, group: "Admin" },
  { path: "/universe-health", label: "Universe Health", icon: Heart, group: "Admin" },
  { path: "/system", label: "System", icon: Activity, group: "Admin" },
];

export function Sidebar() {
  const wheelMode = getWheelPageMode();
  const [showAdvanced, setShowAdvancedState] = useState(getShowAdvanced());
  const wheelVisible = isWheelLinkVisible();

  useEffect(() => {
    setShowAdvancedState(getShowAdvanced());
  }, [wheelVisible]);

  const nav = navBase.filter((item) => {
    if (!("wheel" in item) || !item.wheel) return true;
    return wheelVisible;
  }).map((item) => {
    if ("wheel" in item && item.wheel && wheelMode === "admin") {
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
          return (
            <div key={group} className="space-y-0.5" data-testid={`nav-group-${group.toLowerCase()}`}>
              <div className="px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-400 dark:text-zinc-600">
                {group}
              </div>
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
