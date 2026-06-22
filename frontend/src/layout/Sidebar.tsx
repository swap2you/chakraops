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
    <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex h-12 items-center border-b border-zinc-200 px-3 dark:border-zinc-800">
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">ChakraOps</span>
      </div>
      <nav className="flex-1 space-y-2 overflow-y-auto p-2">
        {GROUP_ORDER.map((group) => {
          const items = nav.filter((item) => item.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group} className="space-y-0.5" data-testid={`nav-group-${group.toLowerCase()}`}>
              <div className="px-2.5 pb-0.5 pt-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-600">
                {group}
              </div>
              {items.map(({ path, label, icon: Icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-white"
                        : "text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
                    }`
                  }
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </NavLink>
              ))}
            </div>
          );
        })}
        {wheelMode === "advanced" && (
          <div className="mt-2 border-t border-zinc-200 px-2.5 py-2 dark:border-zinc-800">
            <label className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400 cursor-pointer">
              <input
                type="checkbox"
                checked={showAdvanced}
                onChange={(e) => {
                  const v = e.target.checked;
                  setShowAdvanced(v);
                  setShowAdvancedState(v);
                }}
                className="rounded border-zinc-300 dark:border-zinc-600"
              />
              Show advanced
            </label>
          </div>
        )}
      </nav>
    </aside>
  );
}
