/** E2E: hyprstart search-bar mic → dictation SDK → transcript in input. */

import { test, expect } from "@playwright/test";

const FAKE_TRANSCRIPT = "hello maya search";

test.describe("startpage mic dictation", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((transcript: string) => {
      class FakeWorkletNode {
        port = { onmessage: null as ((e: MessageEvent) => void) | null };
        connect() {}
        disconnect() {}
      }

      const OriginalCtx = window.AudioContext;
      (window as unknown as { AudioContext: typeof AudioContext }).AudioContext =
        class extends OriginalCtx {
          audioWorklet = {
            addModule: async () => undefined,
          };
          constructor(opts?: AudioContextOptions) {
            super(opts);
          }
        } as typeof AudioContext;

      (window as unknown as { AudioWorkletNode: typeof AudioWorkletNode }).AudioWorkletNode =
        FakeWorkletNode as unknown as typeof AudioWorkletNode;

      const tracks = [{ stop: () => undefined }];
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          getUserMedia: async () => ({ getTracks: () => tracks }),
        },
      });

      (window as unknown as { WebSocket: typeof WebSocket }).WebSocket = class {
        binaryType = "arraybuffer";
        readyState = 1;
        onopen: (() => void) | null = null;
        onmessage: ((ev: MessageEvent) => void) | null = null;
        onerror: (() => void) | null = null;

        constructor(_url: string | URL, _protocols?: string | string[]) {
          queueMicrotask(() => this.onopen?.());
          window.setTimeout(() => {
            const payload = JSON.stringify({ text: transcript, is_final: true });
            this.onmessage?.(new MessageEvent("message", { data: payload }));
          }, 150);
        }

        send() {}
        close() {}
      } as unknown as typeof WebSocket;
    }, FAKE_TRANSCRIPT);
  });

  test("desktop search mic writes transcript into input", async ({ page }) => {
    await page.goto("/");
    const input = page.getByTestId("desktop-search-input");
    const mic = page.getByTestId("desktop-search-mic");
    await expect(mic).toBeVisible();
    await mic.click();
    await expect(input).toHaveValue(FAKE_TRANSCRIPT, { timeout: 10_000 });
  });

  test("launcher mic writes transcript into input", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+Alt+k");
    const input = page.getByTestId("launcher-input");
    const mic = page.getByTestId("launcher-mic");
    await expect(mic).toBeVisible();
    await mic.click();
    await expect(input).toHaveValue(FAKE_TRANSCRIPT, { timeout: 10_000 });
  });
});
