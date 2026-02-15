import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

type ThemeMode = "dark" | "light" | "system";

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const cycle = () => {
    const next: ThemeMode = mode === "dark" ? "light" : mode === "light" ? "system" : "dark";
    setMode(next);
  };
  return (
    <button
      type="button"
      onClick={cycle}
      className="flex h-8 w-8 items-center justify-center rounded border border-zinc-200 bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
      title={`Theme: ${mode} (click to cycle)`}
      aria-label={`Theme: ${mode}. Click to switch.`}
    >
      {mode === "dark" && <Moon className="h-4 w-4" />}
      {mode === "light" && <Sun className="h-4 w-4" />}
      {mode === "system" && <Monitor className="h-4 w-4" />}
    </button>
  );
}
