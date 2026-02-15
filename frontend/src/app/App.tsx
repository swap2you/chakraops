import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { UniversePage } from "@/pages/UniversePage";
import { SymbolDiagnosticsPage } from "@/pages/SymbolDiagnosticsPage";
import { SystemDiagnosticsPage } from "@/pages/SystemDiagnosticsPage";

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
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/universe" element={<UniversePage />} />
            <Route path="/symbol-diagnostics" element={<SymbolDiagnosticsPage />} />
            <Route path="/system" element={<SystemDiagnosticsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
