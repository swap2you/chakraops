/**
 * Phase 8.6: Command palette — Cmd+K / Ctrl+K; quick nav, scenario switch (MOCK), quick actions.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Briefcase,
  BookOpen,
  Bell,
  BarChart3,
  History,
  Search,
  Zap,
  ChevronRight,
  Activity,
} from "lucide-react";
import { useDataMode } from "@/context/DataModeContext";
import { useScenario } from "@/context/ScenarioContext";
import { SCENARIO_LABELS, type ScenarioKey } from "@/mock/scenarios";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { path: "/dashboard", label: "Dashboard", icon: LayoutDashboard, shortcut: "g d" },
  { path: "/positions", label: "Positions", icon: Briefcase, shortcut: "g p" },
  { path: "/journal", label: "Journal", icon: BookOpen, shortcut: "g j" },
  { path: "/notifications", label: "Notifications", icon: Bell, shortcut: "g n" },
  { path: "/history", label: "History", icon: History, shortcut: "g h" },
  { path: "/analytics", label: "Universe", icon: BarChart3, shortcut: "g a" },
  { path: "/analysis", label: "Ticker", icon: Search, shortcut: "g y" },
  { path: "/strategy", label: "Strategy", icon: BookOpen, shortcut: "g s" },
  { path: "/pipeline", label: "Pipeline", icon: BookOpen, shortcut: "g i" },
  { path: "/diagnostics", label: "Diagnostics", icon: Activity, shortcut: "g x" },
] as const;

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { mode } = useDataMode();
  const scenario = useScenario();
  const [query, setQuery] = useState("");
  const isMock = mode === "MOCK";

  const handleSelect = useCallback(
    (path: string) => {
      navigate(path);
      onClose();
    },
    [navigate, onClose]
  );

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (!open) return;
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onClose();
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const filteredNav = query.trim()
    ? NAV_ITEMS.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()))
    : NAV_ITEMS;

  const latestDecisionPath = "/history";
  const hasPositions = (scenario?.bundle?.positions?.length ?? 0) > 0;
  const firstSymbol = hasPositions ? scenario?.bundle?.positions?.[0]?.symbol : null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            role="presentation"
            className="fixed inset-0 z-[100] bg-black/50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-label="Command palette"
            className="fixed left-1/2 top-[20%] z-[101] w-full max-w-lg -translate-x-1/2 rounded-lg border border-border bg-card shadow-xl"
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: "tween", duration: 0.15 }}
          >
            <div className="border-b border-border p-2">
              <input
                type="search"
                placeholder="Navigate or search… (Esc to close)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full rounded-md border-0 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                autoFocus
                aria-label="Command palette search"
              />
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-2">
              <p className="px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Navigation
              </p>
              <ul className="space-y-0.5">
                {filteredNav.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <li key={item.path}>
                      <button
                        type="button"
                        onClick={() => handleSelect(item.path)}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm focus:outline-none focus:ring-2 focus:ring-ring",
                          isActive ? "bg-primary/15 text-primary" : "text-foreground hover:bg-muted/50"
                        )}
                      >
                        <span className="flex items-center gap-2">
                          <Icon className="h-4 w-4" />
                          {item.label}
                        </span>
                        <span className="text-xs text-muted-foreground">{item.shortcut}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              {isMock && scenario && (
                <>
                  <p className="mt-4 px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Scenario (MOCK)
                  </p>
                  <select
                    value={scenario.scenarioKey}
                    onChange={(e) => scenario.setScenarioKey(e.target.value as ScenarioKey)}
                    className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    aria-label="Scenario"
                  >
                    {scenario.scenarioKeys.map((key) => (
                      <option key={key} value={key}>
                        {SCENARIO_LABELS[key]}
                      </option>
                    ))}
                  </select>
                </>
              )}

              <p className="mt-4 px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Quick actions
              </p>
              <ul className="space-y-0.5">
                <li>
                  <button
                    type="button"
                    onClick={() => handleSelect(latestDecisionPath)}
                    className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm text-foreground hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    <span className="flex items-center gap-2">
                      <Zap className="h-4 w-4" />
                      Open latest decision
                    </span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </button>
                </li>
                {firstSymbol && (
                  <li>
                    <button
                      type="button"
                      onClick={() => handleSelect(`/positions?open=${encodeURIComponent(String(firstSymbol))}`)}
                      className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm text-foreground hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      <span className="flex items-center gap-2">
                        <Briefcase className="h-4 w-4" />
                        Open {firstSymbol} position
                      </span>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </li>
                )}
              </ul>

              <p className="mt-4 px-2 py-1 text-xs text-muted-foreground">
                Shortcuts: g d dashboard, g p positions, g j journal, g n notifications, g h history, g a universe, g s strategy, g x diagnostics
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
