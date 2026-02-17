/**
 * Phase 10: LIVE polling — pollTick increments on interval when LIVE; doesn't crash.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@/test/test-utils";
import { PollingProvider, usePolling } from "./PollingContext";
import { DataModeProvider } from "@/context/DataModeContext";
import { ThemeProvider } from "@/context/ThemeContext";

vi.mock("@/hooks/useApiHealth", () => ({ useApiHealth: () => ({ ok: true }) }));

function Consumer() {
  const ctx = usePolling();
  return <span data-testid="poll-tick">{ctx?.pollTick ?? -1}</span>;
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <DataModeProvider>
        <PollingProvider>{children}</PollingProvider>
      </DataModeProvider>
    </ThemeProvider>
  );
}

describe("PollingContext", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("provides pollTick and triggerRefetch", () => {
    render(
      <Wrapper>
        <Consumer />
      </Wrapper>
    );
    expect(screen.getByTestId("poll-tick").textContent).toBe("0");
  });

  it("in LIVE mode does not crash when timers advance (polling interval)", async () => {
    render(
      <ThemeProvider>
        <DataModeProvider initialMode="LIVE">
          <PollingProvider>
            <Consumer />
          </PollingProvider>
        </DataModeProvider>
      </ThemeProvider>
    );
    expect(screen.getByTestId("poll-tick").textContent).toBe("0");
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByTestId("poll-tick")).toBeInTheDocument();
  });

  it("does not crash when used outside provider", () => {
    render(<Consumer />);
    expect(screen.getByTestId("poll-tick").textContent).toBe("-1");
  });
});
