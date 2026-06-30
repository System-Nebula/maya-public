import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const VOICE_PORT = Number(process.env.VA_SERVER_PORT ?? 7862);
const VOICE_BASE = `http://127.0.0.1:${VOICE_PORT}`;
const E2E_ROOT = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],

  use: {
    baseURL: VOICE_BASE,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  webServer: {
    command: `uv run --project packages/maya-voice-stack maya-voice-server --port ${VOICE_PORT}`,
    cwd: path.join(E2E_ROOT, "../.."),
    url: `${VOICE_BASE}/config`,
    timeout: 90_000,
    reuseExistingServer: !process.env.CI,
    env: {
      VA_FAKE_STACK: "1",
      VA_SERVER_PORT: String(VOICE_PORT),
      VA_FAKE_STT_TRANSCRIPT: "hello maya",
      VA_FAKE_LLM_REPLY: "Hi there! Nice to meet you.",
    },
    stdout: "pipe",
    stderr: "pipe",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
