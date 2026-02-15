import { NavLink } from "react-router-dom";
import { LayoutDashboard, Globe, Search, Activity } from "lucide-react";

const nav = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/universe", label: "Universe", icon: Globe },
  { path: "/symbol-diagnostics", label: "Symbol", icon: Search },
  { path: "/system", label: "System", icon: Activity },
];

export function Sidebar() {
  return (
    <aside className="w-48 border-r border-zinc-800 bg-zinc-950 p-2">
      <nav className="space-y-0.5">
        {nav.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
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
