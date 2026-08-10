import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AppLayout } from "@/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { OpportunitiesPage } from "@/pages/OpportunitiesPage";
import { UniversePage } from "@/pages/UniversePage";
import { SymbolDiagnosticsPage } from "@/pages/SymbolDiagnosticsPage";
import { SystemDiagnosticsPage } from "@/pages/SystemDiagnosticsPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { PositionsPage } from "@/pages/PositionsPage";
import { WheelPage } from "@/pages/WheelPage";
import { JournalPage } from "@/pages/JournalPage";
import { TradeTicketPage } from "@/pages/TradeTicketPage";
import { TodayPage } from "@/pages/TodayPage";
import { WeeklyReviewPage } from "@/pages/WeeklyReviewPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { BacktestPage } from "@/pages/BacktestPage";
import { LearnPage } from "@/pages/LearnPage";
import { PaperPage } from "@/pages/PaperPage";
import { UniverseAdminPage } from "@/pages/UniverseAdminPage";
import { UniverseHealthPage } from "@/pages/UniverseHealthPage";
import { getWheelPageMode } from "@/config/features";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // R48: prefer persisted/read-model freshness windows; avoid refetch storms on focus
      staleTime: 60_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/opportunities" element={<OpportunitiesPage />} />
              <Route path="/universe" element={<UniversePage />} />
              <Route path="/symbol-diagnostics" element={<SymbolDiagnosticsPage />} />
              <Route path="/system" element={<SystemDiagnosticsPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/journal" element={<JournalPage />} />
              <Route path="/learn" element={<LearnPage />} />
              <Route path="/ticket" element={<TradeTicketPage />} />
              <Route path="/today" element={<TodayPage />} />
              <Route path="/weekly" element={<WeeklyReviewPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/paper" element={<PaperPage />} />
              <Route path="/universe-admin" element={<UniverseAdminPage />} />
              <Route path="/universe-health" element={<UniverseHealthPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/positions" element={<PositionsPage />} />
              {getWheelPageMode() !== "hidden" ? (
                <Route path="/wheel" element={<WheelPage />} />
              ) : (
                <Route path="/wheel" element={<Navigate to="/" replace />} />
              )}
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
