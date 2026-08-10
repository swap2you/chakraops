import { test, expect } from "@playwright/test";

test.describe("R49 accessibility basics", () => {
  test("skip link and main landmark exist", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("skip-to-content")).toBeAttached();
    await expect(page.locator("#main-content")).toBeVisible();
  });

  test("primary nav groups present", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-group-command-center")).toBeVisible();
    await expect(page.getByTestId("nav-group-portfolio")).toBeVisible();
    await expect(page.getByTestId("nav-group-operations")).toBeVisible();
  });
});
