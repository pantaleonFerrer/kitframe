import { test, expect } from "@playwright/test";

test.describe("core path smoke", () => {
  test("login page renders", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /Entrar en Kitframe/i })).toBeVisible();
  });
});
