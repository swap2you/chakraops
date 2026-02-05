import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { DashboardPage } from "./DashboardPage";

describe("DashboardPage", () => {
  it("renders without throwing", () => {
    expect(() => render(<DashboardPage />)).not.toThrow();
  });

  it("shows decision region", () => {
    render(<DashboardPage />);
    const region = screen.getByRole("region", { name: /decision/i });
    expect(region).toBeInTheDocument();
  });

  it("shows trade plan region", () => {
    render(<DashboardPage />);
    const region = screen.getByRole("region", { name: /trade plan/i });
    expect(region).toBeInTheDocument();
  });

  it("shows daily overview region", () => {
    render(<DashboardPage />);
    const region = screen.getByRole("region", { name: /daily overview/i });
    expect(region).toBeInTheDocument();
  });
});
