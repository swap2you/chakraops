/**
 * Phase 7: Simple access gate — password/token prompt before app renders.
 * When VITE_APP_PASSWORD is set, user must enter it to unlock; state stored in sessionStorage.
 * When unset (e.g. local dev), children render immediately.
 */
import { useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "chakraops_unlocked";

function getExpectedPassword(): string | undefined {
  const env = (import.meta as unknown as { env?: { VITE_APP_PASSWORD?: string } }).env;
  return env?.VITE_APP_PASSWORD?.trim() || undefined;
}

function getStoredUnlocked(): boolean {
  try {
    return sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function setStoredUnlocked(value: boolean): void {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, "1");
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function AccessGate({ children }: { children: React.ReactNode }) {
  const expected = getExpectedPassword();
  const [unlocked, setUnlocked] = useState(() => !expected || getStoredUnlocked());
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expected) return;
    if (getStoredUnlocked()) setUnlocked(true);
  }, [expected]);

  const submit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      if (!expected) {
        setUnlocked(true);
        return;
      }
      if (password.trim() === expected) {
        setStoredUnlocked(true);
        setUnlocked(true);
      } else {
        setError("Incorrect password or token.");
      }
    },
    [password, expected]
  );

  if (!expected) {
    return <>{children}</>;
  }

  if (unlocked) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-sm">
        <h1 className="mb-2 text-lg font-semibold text-foreground">ChakraOps</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Enter the access password or token to continue.
        </p>
        <form onSubmit={submit} className="space-y-3">
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password or token"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Access password"
          />
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            Continue
          </button>
        </form>
      </div>
    </div>
  );
}
