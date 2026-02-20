import { useState, useEffect } from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Globe, Search, Activity, PieChart, Bell, RotateCcw } from "lucide-react";
import { getWheelPageMode, isWheelLinkVisible, getShowAdvanced, setShowAdvanced } from "@/config/features";

const navBase = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/universe", label: "Universe", icon: Globe },
  { path: "/symbol-diagnostics", label: "Symbol", icon: Search },
  { path: "/wheel", label: "Wheel", icon: RotateCcw, wheel: true },
  { path: "/portfolio", label: "Account & Portfolio", icon: PieChart },
  { path: "/notifications", label: "Notifications", icon: Bell },
  { path: "/system", label: "System", icon: Activity },
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
      <nav className="flex-1 space-y-0.5 p-2">
        {nav.map(({ path, label, icon: Icon }) => (
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
