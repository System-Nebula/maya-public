/** Voice stack web UI — SSE event flow with WAV benchmark replay. */

import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const VOICE_PORT = Number(process.env.VA_SERVER_PORT ?? 7861);
const VOICE_BASE = `http://127.0.0.1:${VOICE_PORT}`;
const E2E_ROOT = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_WAV = path.join(
  E2E_ROOT,
  "../../packages/maya-voice-stack/fixtures/audio/hello_maya.wav",
);

async function waitForVoiceReady(request: import("@playwright/test").APIRequestContext) {
  for (let i = 0; i < 30; i++) {
    const res = await request.get(`${VOICE_BASE}/config`);
    if (res.ok()) {
      const body = await res.json();
      if (body.ready) return body;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("voice server not ready");
}

test.describe("voice stack web transfer", () => {
  test("page loads and reports ready", async ({ page, request }) => {
    await waitForVoiceReady(request);
    await page.goto(VOICE_BASE);
    await expect(page).toHaveTitle(/voice|qwen|maya/i);
  });

  test("mic click starts demo session and shows transcript", async ({ page, request }) => {
    test.setTimeout(60_000);
    await waitForVoiceReady(request);
    await page.goto(VOICE_BASE);
    await expect(page.locator("#micBtn")).toBeEnabled({ timeout: 15_000 });
    await page.locator("#micBtn").click();
    await expect(page.locator(".msg.user")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".msg.ai")).toBeVisible({ timeout: 15_000 });
  });

  test("benchmark turn emits user and ai SSE events", async ({ request }) => {
    test.setTimeout(60_000);
    await waitForVoiceReady(request);
    expect(fs.existsSync(FIXTURE_WAV)).toBeTruthy();

    const events: Array<Record<string, unknown>> = [];
    const controller = new AbortController();
    const readerTask = (async () => {
      const res = await fetch(`${VOICE_BASE}/events`, { signal: controller.signal });
      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          events.push(JSON.parse(line.slice(6)));
        }
      }
    })();

    const wav = fs.readFileSync(FIXTURE_WAV);
    const upload = await request.post(`${VOICE_BASE}/benchmark/turn`, {
      multipart: {
        file: {
          name: "hello_maya.wav",
          mimeType: "audio/wav",
          buffer: wav,
        },
      },
    });
    expect(upload.ok()).toBeTruthy();
    const body = await upload.json();
    expect(body.ok).toBeTruthy();
    expect(body.user_text).toBeTruthy();
    expect(body.assistant_text).toBeTruthy();
    expect(body.timings.full_turn_ms).toBeGreaterThan(0);

    await new Promise((r) => setTimeout(r, 2000));
    controller.abort();
    await readerTask.catch(() => {});

    const types = events.map((e) => e.type);
    expect(types).toContain("user");
    expect(types).toContain("ai");
    expect(types).toContain("status");
  });
});
