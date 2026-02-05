import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { HistoryPage } from "./HistoryPage";

describe("HistoryPage", () => {
  it("renders without throwing", () => {
    expect(() => render(<HistoryPage />)).not.toThrow();
  });

  it("shows Decision history heading", () => {
    render(<HistoryPage />);
    expect(screen.getByRole("heading", { name: /decision history/i })).toBeInTheDocument();
  });

  it("shows Filters region", () => {
    render(<HistoryPage />);
    const region = screen.getByRole("region", { name: /filters/i });
    expect(region).toBeInTheDocument();
  });

  it("shows decision type filter", () => {
    render(<HistoryPage />);
    const select = screen.getByRole("combobox", { name: /decision type/i });
    expect(select).toBeInTheDocument();
  });

  it("filtering by decision type updates list", () => {
    render(<HistoryPage />);
    const select = screen.getByRole("combobox", { name: /decision type/i });
    fireEvent.change(select, { target: { value: "NO_TRADE" } });
    const list = screen.getByRole("region", { name: /decision list/i });
    expect(list).toBeInTheDocument();
  });

  it("date filter out of range shows empty state", () => {
    render(<HistoryPage />);
    const fromInput = screen.getByLabelText(/from date/i);
    const toInput = screen.getByLabelText(/to date/i);
    fireEvent.change(fromInput, { target: { value: "2030-01-01" } });
    fireEvent.change(toInput, { target: { value: "2030-12-31" } });
    expect(screen.getByText(/no decisions match the current filters/i)).toBeInTheDocument();
  });

  it("clicking a history entry opens detail drawer", () => {
    render(<HistoryPage />);
    const listButtons = screen.getAllByRole("button").filter((b) => b.closest("ul"));
    const firstEntry = listButtons[0];
    expect(firstEntry).toBeDefined();
    fireEvent.click(firstEntry!);
    const dialog = screen.getByRole("dialog", { name: /decision detail/i });
    expect(dialog).toBeInTheDocument();
  });
});
