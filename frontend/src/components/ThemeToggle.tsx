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
      className="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 transition-all duration-150 hover:bg-zinc-100 hover:text-zinc-900 active:scale-95 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100"
      title={`Theme: ${mode} (click to cycle)`}
      aria-label={`Theme: ${mode}. Click to switch.`}
    >
      {mode === "dark" && <Moon className="h-4 w-4" />}
      {mode === "light" && <Sun className="h-4 w-4" />}
      {mode === "system" && <Monitor className="h-4 w-4" />}
    </button>
  );
}
