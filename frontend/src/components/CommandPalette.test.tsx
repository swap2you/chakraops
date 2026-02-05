import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { CommandPalette } from "./CommandPalette";

describe("CommandPalette", () => {
  it("when open shows navigation items", () => {
    render(<CommandPalette open onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: /command palette/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/navigate or search/i)).toBeInTheDocument();
  });

  it("when closed does not show dialog", () => {
    render(<CommandPalette open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog", { name: /command palette/i })).not.toBeInTheDocument();
  });

  it("clicking Dashboard navigates", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const btn = screen.getByRole("button", { name: /dashboard/i });
    fireEvent.click(btn);
    expect(window.location.pathname).toBe("/dashboard");
  });
});
