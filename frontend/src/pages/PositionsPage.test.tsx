import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { PositionsPage } from "./PositionsPage";

describe("PositionsPage", () => {
  it("renders without throwing", () => {
    expect(() => render(<PositionsPage />)).not.toThrow();
  });

  it("shows Positions heading", () => {
    render(<PositionsPage />);
    expect(screen.getByRole("heading", { name: /positions/i })).toBeInTheDocument();
  });

  it("shows table or empty state", () => {
    render(<PositionsPage />);
    const table = document.querySelector("table");
    const empty = screen.queryByText(/no positions/i);
    expect(table != null || empty != null).toBe(true);
  });

  it("clicking a row opens position detail drawer", () => {
    render(<PositionsPage />);
    const rowButton = screen.getByRole("button", { name: /SPY.*CSP.*OPEN/i });
    fireEvent.click(rowButton);
    const dialog = screen.getByRole("dialog", { name: /position detail/i });
    expect(dialog).toBeInTheDocument();
  });
});
