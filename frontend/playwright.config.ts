import { defineConfig, devices } from "@playwright/test";

/**
 * Permanent ChakraOps browser/E2E + screenshot harness (R41).
 * Default: Chromium against local frontend 18873 / backend 18800.
 * Safe: no broker writes; mutation tests must use isolated storage.
 */
const FRONTEND = process.env.CHAKRAOPS_FRONTEND_URL || "http://127.0.0.1:18873";
const BACKEND = process.env.CHAKRAOPS_BACKEND_URL || "http://127.0.0.1:18800";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",
  use: {
    baseURL: FRONTEND,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    extraHTTPHeaders: process.env.VITE_UI_KEY
      ? { "x-ui-key": process.env.VITE_UI_KEY }
      : {},
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  metadata: {
    backend: BACKEND,
    manual_only: true,
    trade_execution: false,
    no_broker_writes: true,
  },
  webServer: process.env.CHAKRAOPS_E2E_NO_WEBSERVER
    ? undefined
    : {
        command: "npm run dev -- --host 127.0.0.1 --port 18873",
        url: FRONTEND,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
