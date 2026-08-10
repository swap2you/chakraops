import { test, expect, type Page, type ConsoleMessage, type Request } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { CANONICAL_ROUTES, BACKEND_URL } from "./routes";

const EVIDENCE_DIR = path.resolve(
  process.env.CHAKRAOPS_E2E_EVIDENCE ||
    path.join("..", "out", "verification", "R41", "screenshots")
);

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true });
}

async function collectConsole(page: Page) {
  const errors: string[] = [];
  const warnings: string[] = [];
  page.on("console", (msg: ConsoleMessage) => {
    const t = msg.type();
    const text = msg.text();
    if (t === "error") errors.push(text);
    if (t === "warning") warnings.push(text);
  });
  return { errors, warnings };
}

async function collectFailedRequests(page: Page) {
  const failed: Array<{ url: string; status?: number; failure?: string }> = [];
  page.on("requestfailed", (req: Request) => {
    failed.push({ url: req.url(), failure: req.failure()?.errorText });
  });
  page.on("response", (res) => {
    // Capture 4xx/5xx so C-1 style console 404s are attributable by URL
    if (res.status() >= 400) {
      failed.push({ url: res.url(), status: res.status() });
    }
  });
  return failed;
}

test.describe("R41 route screenshot pack", () => {
  test.beforeAll(() => {
    ensureDir(EVIDENCE_DIR);
  });

  test("backend health and safety smoke", async ({ request }) => {
    const health = await request.get(`${BACKEND_URL}/api/healthz`);
    expect(health.ok()).toBeTruthy();
    const ops = await request.get(`${BACKEND_URL}/api/operations/status`);
    expect(ops.ok()).toBeTruthy();
    const body = await ops.json();
    expect(body.manual_only).toBe(true);
    expect(body.trade_execution).toBe(false);
    expect(body.scheduler?.master_enabled).toBe(false);
    expect(body.scheduler?.legacy_schedulers_enabled).toBe(false);
    expect(body.scheduler?.running).toBe(false);
  });

  for (const route of CANONICAL_ROUTES) {
    test(`route ${route.path} — ${route.name}`, async ({ page }) => {
      const consoleBag = await collectConsole(page);
      const failed = await collectFailedRequests(page);

      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(800);

      // Direct refresh
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForTimeout(500);

      if (route.pageTestId) {
        await expect(page.getByTestId(route.pageTestId)).toBeVisible({ timeout: 20_000 });
      } else {
        await expect(page.locator("main, [class*='space-y']").first()).toBeVisible({ timeout: 20_000 });
      }

      const slug = route.path === "/" ? "home" : route.path.replace(/\//g, "_").replace(/^_/, "");
      const shotPath = path.join(EVIDENCE_DIR, `${slug}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });

      // Soft assert: no page crash banners; console errors recorded in evidence
      const summary = {
        route: route.path,
        name: route.name,
        screenshot: shotPath,
        console_errors: consoleBag.errors.slice(0, 20),
        console_warnings: consoleBag.warnings.slice(0, 20),
        failed_requests: failed.filter((f) => !f.url.includes("favicon")).slice(0, 20),
      };
      fs.writeFileSync(
        path.join(EVIDENCE_DIR, `${slug}.meta.json`),
        JSON.stringify(summary, null, 2),
        "utf-8"
      );

      // Fatal: uncaught page errors that blank the app
      const bodyText = await page.locator("body").innerText();
      expect(bodyText.toLowerCase()).not.toContain("application error");
    });
  }

  test("theme toggle primary screens light/dark", async ({ page }) => {
    ensureDir(EVIDENCE_DIR);
    await page.goto("/");
    await page.waitForTimeout(600);
    // Theme toggle is in header — click until dark/light applied
    const toggle = page.getByRole("button", { name: /theme|dark|light|system/i }).first();
    if (await toggle.count()) {
      await toggle.click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(EVIDENCE_DIR, "home_theme_toggle.png"), fullPage: true });
    }
  });

  test("no broker write affordance on ticket", async ({ page }) => {
    await page.goto("/ticket");
    await page.waitForTimeout(500);
    const body = (await page.locator("body").innerText()).toLowerCase();
    expect(body).not.toMatch(/send order to broker|place order at robinhood|submit to broker/);
  });
});
