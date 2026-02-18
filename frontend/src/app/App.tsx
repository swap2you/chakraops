import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AppLayout } from "@/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { UniversePage } from "@/pages/UniversePage";
import { SymbolDiagnosticsPage } from "@/pages/SymbolDiagnosticsPage";
import { SystemDiagnosticsPage } from "@/pages/SystemDiagnosticsPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { WheelPage } from "@/pages/WheelPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
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
              <Route path="/universe" element={<UniversePage />} />
              <Route path="/symbol-diagnostics" element={<SymbolDiagnosticsPage />} />
              <Route path="/system" element={<SystemDiagnosticsPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/wheel" element={<WheelPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
