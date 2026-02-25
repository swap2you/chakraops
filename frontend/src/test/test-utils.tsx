import { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { DataModeProvider } from "@/context/DataModeContext";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { ThemeProvider } from "@/context/ThemeContext";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

/** Clear query cache between tests to avoid stale data when mocks change (e.g. Shares tab tests). */
export function clearTestQueryCache() {
  queryClient.clear();
}

/** Create a new QueryClient for tests that need full cache isolation (e.g. Shares tab with initialTabForTest). */
export function createFreshQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DataModeProvider>
          <ScenarioProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</BrowserRouter>
          </ScenarioProvider>
        </DataModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/** Use when you need a specific initial URL (e.g. ?tab=Shares); avoids pushState timing issues. */
function AllProvidersWithInitialEntry({ children, initialEntry }: { children: React.ReactNode; initialEntry: string }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DataModeProvider>
          <ScenarioProvider>
            <MemoryRouter initialEntries={[initialEntry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</MemoryRouter>
          </ScenarioProvider>
        </DataModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function customRender(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, {
    wrapper: AllProviders,
    ...options,
  });
}

/** Render with a fresh QueryClient so no cached data from previous tests is used. */
function renderWithFreshClient(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  const freshClient = createFreshQueryClient();
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={freshClient}>
      <ThemeProvider>
        <DataModeProvider>
          <ScenarioProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</BrowserRouter>
          </ScenarioProvider>
        </DataModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper, ...options });
}

/** Render with a specific initial route (e.g. "/symbol-diagnostics?symbol=WMT&tab=Shares"). */
function renderWithRoute(ui: ReactElement, initialEntry: string, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, {
    wrapper: ({ children }) => <AllProvidersWithInitialEntry initialEntry={initialEntry}>{children}</AllProvidersWithInitialEntry>,
    ...options,
  });
}

export * from "@testing-library/react";
export { customRender as render, renderWithRoute, renderWithFreshClient };
