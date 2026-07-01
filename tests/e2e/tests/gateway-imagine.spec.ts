/** E2E: gateway imagine + API routing smoke (DB-free). */

import { test, expect } from "@playwright/test";

test.describe("gateway routing", () => {
  test("health endpoint responds", async ({ request }) => {
    const resp = await request.get("/api/status/health");
    expect(resp.ok()).toBeTruthy();
  });

  test("imagine leaderboard JSON", async ({ request }) => {
    const resp = await request.get("/gateway/imagine/leaderboard?format=json");
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty("candidates");
  });

  test("SPA catchall does not shadow gateway routes", async ({ request }) => {
    const resp = await request.get("/gateway/imagine/workflows");
    expect(resp.ok()).toBeTruthy();
  });
});
