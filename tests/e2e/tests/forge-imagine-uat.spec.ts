/** Browser UAT: Forge imagine composer → generate → vote → resolved. */

import { test, expect } from "@playwright/test";

async function waitForImagineReady(page: import("@playwright/test").Page) {
  await page.goto("/gateway/imagine");
  await page.waitForFunction(() => {
    const indicator = document.querySelector(".sse-indicator");
    const text = indicator?.textContent?.trim() ?? "";
    return text === "live" || text === "polling";
  });
}

test.describe("forge imagine UAT", () => {
  test("open page shows composer and empty feed shell", async ({ page }) => {
    await waitForImagineReady(page);
    await expect(page.locator(".imagine-composer input[name=prompt]")).toBeVisible();
    await expect(page.locator("#gateway-feed")).toBeVisible();
    await expect(page.locator("#imagine-empty")).toBeVisible();
    await expect(page.locator("#imagine-leaderboard")).toHaveCount(1);
    await expect(page.locator(".sse-indicator")).toContainText(/live|polling/);
  });

  test("generate prompt, vote, and resolve battle card", async ({ page }) => {
    test.setTimeout(60_000);
    await waitForImagineReady(page);

    const prompt = "a gopher holding a golden microphone";
    await page.locator(".imagine-composer input[name=prompt]").fill(prompt);
    await page.locator(".imagine-composer input[name=prompt]").press("Enter");

    const card = page.locator(".arena-card", { hasText: prompt });
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card.locator(".arena-prompt")).toContainText(prompt);

    await expect(card.locator(".arena-vote-btn").first()).toBeVisible({ timeout: 30_000 });

    await card.locator('[data-choice="a"]').click();

    await expect(card).toHaveClass(/arena-resolved/, { timeout: 15_000 });
    await expect(card.locator(".status-pill.completed")).toContainText("resolved");
    await expect(card.locator(".arena-reveal").first()).toBeVisible();
  });

  test("poll fallback works when SSE is blocked", async ({ page, context }) => {
    test.setTimeout(60_000);
    await context.route("**/gateway/imagine/queue/stream", (route) => route.abort());

    await waitForImagineReady(page);
    await expect(page.locator(".sse-indicator")).toContainText("polling");

    await page.locator(".imagine-composer input[name=prompt]").fill("a cat");
    await page.locator(".imagine-composer button[type=submit]").click();

    const card = page.locator(".arena-card", { hasText: "a cat" });
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card.locator(".arena-vote-btn").first()).toBeVisible({ timeout: 45_000 });
  });
});
