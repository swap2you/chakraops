import { useState, useEffect, useCallback } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { DataModeProvider } from "@/context/DataModeContext";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { PollingProvider } from "@/context/PollingContext";
import { CommandBar } from "@/components/CommandBar";
import { CommandPalette } from "@/components/CommandPalette";
import { DashboardPage } from "@/pages/DashboardPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { JournalPage } from "@/pages/JournalPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { DiagnosticsPage } from "@/pages/DiagnosticsPage";
import { StrategyPage } from "@/pages/StrategyPage";
import { PipelinePage } from "@/pages/PipelinePage";
import { AccountsPage } from "@/pages/AccountsPage";
import { TrackedPositionsPage } from "@/pages/TrackedPositionsPage";
import { AccessGate } from "@/components/AccessGate";

const SHORTCUT_PATHS: Record<string, string> = {
  d: "/dashboard",
  p: "/positions",
  j: "/journal",
  n: "/notifications",
  h: "/history",
  a: "/analytics",
  x: "/diagnostics",
  s: "/strategy",
  i: "/pipeline",
  c: "/accounts",
  t: "/tracked-positions",
};

function KeyboardShortcuts({ onOpenPalette }: { onOpenPalette: () => void }) {
  const navigate = useNavigate();
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onOpenPalette();
        return;
      }
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (e.key === "g" && !e.repeat) {
        const next = (e2: KeyboardEvent) => {
          const path = SHORTCUT_PATHS[e2.key.toLowerCase()];
          if (path) {
            e2.preventDefault();
            navigate(path);
          }
          window.removeEventListener("keydown", next);
        };
        window.addEventListener("keydown", next, { once: true });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate, onOpenPalette]);
  return null;
}

function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <KeyboardShortcuts onOpenPalette={openPalette} />
      <CommandBar />
      <main className="flex-1">
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/positions" element={<PositionsPage />} />
          <Route path="/journal" element={<JournalPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route path="/strategy" element={<StrategyPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/tracked-positions" element={<TrackedPositionsPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

export default function App() {
  return (
    <AccessGate>
      <ThemeProvider>
        <DataModeProvider>
          <ScenarioProvider>
            <PollingProvider>
              <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
                <AppShell />
              </BrowserRouter>
            </PollingProvider>
          </ScenarioProvider>
        </DataModeProvider>
      </ThemeProvider>
    </AccessGate>
  );
}
