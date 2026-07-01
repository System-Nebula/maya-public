import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.MAYA_GATEWAY_PORT ?? 8765);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const E2E_ROOT = path.dirname(fileURLToPath(import.meta.url));
const IMAGE_ROOT = path.join(E2E_ROOT, ".artifacts", "maya-image");

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  webServer: {
    // Launch the maya-gateway via uv from the repo root.
    command: `uv run --quiet maya-gateway`,
    cwd: "../..",
    url: `${BASE_URL}/`,
    timeout: 60_000,
    reuseExistingServer: !process.env.CI,
    env: {
      PORT: String(PORT),
      ENV: "production",
      MAYA_FAKE_COMFY: "1",
      MAYA_IMAGE_ROOT: IMAGE_ROOT,
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
