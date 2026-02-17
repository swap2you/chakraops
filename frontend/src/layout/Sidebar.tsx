import { NavLink } from "react-router-dom";
import { LayoutDashboard, Globe, Search, Activity, PieChart, Bell } from "lucide-react";

const nav = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/universe", label: "Universe", icon: Globe },
  { path: "/symbol-diagnostics", label: "Symbol", icon: Search },
  { path: "/portfolio", label: "Portfolio", icon: PieChart },
  { path: "/notifications", label: "Notifications", icon: Bell },
  { path: "/system", label: "System", icon: Activity },
];

export function Sidebar() {
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
      </nav>
    </aside>
  );
}
