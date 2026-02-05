import { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { DataModeProvider } from "@/context/DataModeContext";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { ThemeProvider } from "@/context/ThemeContext";

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <DataModeProvider>
        <ScenarioProvider>
          <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</BrowserRouter>
        </ScenarioProvider>
      </DataModeProvider>
    </ThemeProvider>
  );
}

function customRender(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, {
    wrapper: AllProviders,
    ...options,
  });
}

export * from "@testing-library/react";
export { customRender as render };
