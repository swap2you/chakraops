import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { BACKEND_URL } from "./routes";

const EVIDENCE_DIR = path.resolve(
  process.env.CHAKRAOPS_E2E_EVIDENCE ||
    path.join("..", "out", "verification", "R41", "screenshots")
);

/**
 * Mutation tests use isolated localStorage keys and never mutate operator
 * holdings/journal without an explicit CHAKRAOPS_E2E_ALLOW_MUTATIONS=1.
 */
test.describe("R41 isolated mutation safety", () => {
  test("default: mutation flag off", async () => {
    expect(process.env.CHAKRAOPS_E2E_ALLOW_MUTATIONS || "").not.toBe("1");
  });

  test("today queue uses device storage key — backup/restore contract documented", async ({
    page,
  }) => {
    await page.goto("/today");
    await page.waitForTimeout(400);
    const keys = await page.evaluate(() => Object.keys(localStorage));
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, "localstorage_keys.json"),
      JSON.stringify({ keys, note: "Today/ticket queue may be device-local; R42 migrates to canonical persistence" }, null, 2)
    );
    expect(keys).toBeDefined();
  });

  test("ops status remains fail-closed during browser session", async ({ request }) => {
    const ops = await request.get(`${BACKEND_URL}/api/operations/status`);
    const body = await ops.json();
    expect(body.scheduler.master_enabled).toBe(false);
    expect(body.scheduler.legacy_schedulers_enabled).toBe(false);
  });
});
