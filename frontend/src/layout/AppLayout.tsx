import { Outlet } from "react-router-dom";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        <header className="sticky top-0 z-10 flex shrink-0 items-center justify-end gap-2 border-b border-zinc-200 bg-white px-4 py-2 dark:border-zinc-800 dark:bg-zinc-950">
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-auto px-6 py-6 lg:px-10">
          <div className="mx-auto max-w-screen-2xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
