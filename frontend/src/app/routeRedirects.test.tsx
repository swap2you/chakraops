// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
/** R56: route redirects — Positions → Portfolio holdings. */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function RedirectHarness({ initial }: { initial: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/portfolio" element={<div data-testid="page-portfolio">Portfolio</div>} />
          <Route path="/positions" element={<Navigate to="/portfolio?tab=holdings" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("R56 route redirects", () => {
  it("/positions redirects to portfolio holdings", async () => {
    render(<RedirectHarness initial="/positions" />);
    await waitFor(() => {
      expect(screen.getByTestId("page-portfolio")).toBeInTheDocument();
    });
  });
});
