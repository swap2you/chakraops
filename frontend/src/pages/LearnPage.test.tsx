/**
 * R27.6: Learn page — headings/sections, internal links; no FAIL/WARN in document.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { LearnPage } from "./LearnPage";

describe("LearnPage", () => {
  it("renders headings and sections", () => {
    render(<LearnPage />);
    expect(screen.getByRole("heading", { name: /^Learn$/i })).toBeInTheDocument();
    expect(screen.getByTestId("learn-daily-routine")).toBeInTheDocument();
    expect(screen.getByTestId("learn-does-doesnot")).toBeInTheDocument();
    expect(screen.getByTestId("learn-key-terms")).toBeInTheDocument();
    expect(screen.getByTestId("learn-mistakes")).toBeInTheDocument();
    expect(screen.getByTestId("learn-links")).toBeInTheDocument();
    expect(screen.getByText("Daily routine (10–15 min)")).toBeInTheDocument();
    expect(screen.getByText("What the system does / does not do")).toBeInTheDocument();
    expect(screen.getByText("Key terms")).toBeInTheDocument();
    expect(screen.getByText("Common mistakes to avoid")).toBeInTheDocument();
    expect(screen.getByText("Links")).toBeInTheDocument();
  });

  it("renders internal links to Today, Ticket, Journal, Reports, System", () => {
    render(<LearnPage />);
    expect(screen.getAllByRole("link", { name: /today/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("link", { name: /ticket/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("link", { name: /journal/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("link", { name: /reports/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /system diagnostics/i })).toBeInTheDocument();
  });

  it("document.textContent does not contain FAIL or WARN (R27.6 safety)", () => {
    const { container } = render(<LearnPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
