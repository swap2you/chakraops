/**
 * R23.4: Copilot panel — renders, chips send request, answer and copy shown.
 * R23.4.1: Error banner when API returns error_code (e.g. COPILOT_AUTH_FAILED).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { CopilotPanel } from "./CopilotPanel";
import { ApiError } from "@/api/client";

const mockApiPost = vi.fn();
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    apiPost: (...args: unknown[]) => mockApiPost(...args),
  };
});

describe("CopilotPanel R23.4", () => {
  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiPost.mockResolvedValue({
      answer_markdown: "The symbol is not eligible because regime is DOWN.",
      citations: [{ tool: "get_symbol_diagnostics", at: "a1b2" }],
      followups: ["What delta missed the band?"],
      used_tools: ["get_symbol_diagnostics"],
      snapshot_used: false,
      request_id: "req-123",
    });
  });

  it("renders panel with symbol and conversation id", () => {
    render(<CopilotPanel symbol="NVDA" conversationId="copilot-NVDA" />);
    expect(screen.getByRole("heading", { name: /Copilot/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Ask about this symbol/)).toBeInTheDocument();
  });

  it("shows default prompt chips", () => {
    render(<CopilotPanel symbol="WMT" conversationId="copilot-WMT" />);
    expect(screen.getByText("Why is this symbol not eligible?")).toBeInTheDocument();
    expect(screen.getByText("What delta missed the band and by how much?")).toBeInTheDocument();
  });

  it("sends request when chip is clicked and renders answer", async () => {
    render(<CopilotPanel symbol="NVDA" conversationId="copilot-NVDA" />);
    const chip = screen.getByText("Why is this symbol not eligible?");
    fireEvent.click(chip);
    expect(mockApiPost).toHaveBeenCalledWith(
      expect.stringContaining("/api/ui/copilot/ask"),
      expect.objectContaining({
        symbol: "NVDA",
        question: "Why is this symbol not eligible?",
        conversation_id: "copilot-NVDA",
        mode: "symbol",
      })
    );
    await screen.findByText(/not eligible because regime is DOWN/i);
    expect(screen.getByText(/Copy answer/i)).toBeInTheDocument();
  });

  it("submits input on send and shows answer markdown", async () => {
    render(<CopilotPanel symbol="SPY" conversationId="copilot-SPY" />);
    const input = screen.getByPlaceholderText(/Ask about this symbol/);
    fireEvent.change(input, { target: { value: "What is my exposure?" } });
    fireEvent.submit(input.closest("form")!);
    expect(mockApiPost).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ question: "What is my exposure?" })
    );
    await screen.findByText(/not eligible because regime is DOWN/i);
  });

  it("R23.4.1: shows Copilot unavailable banner and fix text when API returns error_code COPILOT_AUTH_FAILED", async () => {
    mockApiPost.mockRejectedValue(
      new ApiError("API 502: Bad Gateway", 502, {
        error_code: "COPILOT_AUTH_FAILED",
        message: "Copilot authentication failed. Verify COPILOT_OPENAI_API_KEY on the server and restart.",
      })
    );
    render(<CopilotPanel symbol="NVDA" conversationId="copilot-NVDA" />);
    fireEvent.click(screen.getByText("Why is this symbol not eligible?"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Copilot unavailable");
    expect(alert).toHaveTextContent("Copilot authentication failed");
    expect(alert).toHaveTextContent("Set COPILOT_OPENAI_API_KEY in backend env and restart uvicorn");
  });
});
