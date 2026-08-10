import { Outlet, useLocation } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NotificationBell } from "@/components/NotificationBell";
import { AfterHoursBanner } from "@/components/AfterHoursBanner";
import { EvalStatusIndicator } from "@/components/EvalStatusIndicator";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const location = useLocation();
  return (
    <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-emerald-600 focus:px-3 focus:py-2 focus:text-white"
        data-testid="skip-to-content"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-10 flex h-14 shrink-0 items-center justify-end gap-3 border-b border-zinc-200/80 px-4 dark:border-zinc-800/80">
          <EvalStatusIndicator />
          <NotificationBell />
          <ThemeToggle />
        </header>
        <AfterHoursBanner />
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-auto px-6 py-6 lg:px-10 outline-none">
          {/* Re-keying by pathname restarts the entrance animation on navigation. */}
          <div key={location.pathname} className="animate-fade-up mx-auto max-w-screen-2xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
