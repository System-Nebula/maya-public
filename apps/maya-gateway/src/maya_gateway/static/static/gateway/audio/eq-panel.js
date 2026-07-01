// eq-panel.js — Alpine eqPanel stub (fake spectrum from /api/audio/spectrum).
// Full EqVisualizer port from voice-stack eq-ui.js lands in phase 2.

function drawFakeSpectrum(canvas, bands) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const barW = w / Math.max(bands.length, 1);
  bands.forEach((b, i) => {
    const level = Math.min(1, Math.max(0, b.level ?? 0));
    const bh = level * (h - 8);
    ctx.fillStyle = "rgba(139, 92, 246, 0.75)";
    ctx.fillRect(i * barW + 1, h - bh, barW - 2, bh);
  });
}

export function eqPanelFactory(opts = {}) {
  return {
    preset: "flat",
    enabled: true,
    stub: true,
    _timer: null,

    async init() {
      this.$nextTick(() => this.refresh());
      this._timer = setInterval(() => this.refresh(), opts.pollMs ?? 200);
    },

    destroy() {
      if (this._timer) clearInterval(this._timer);
    },

    async refresh() {
      const canvas = this.$refs?.eqCanvas;
      if (!canvas) return;
      try {
        const r = await fetch(opts.spectrumUrl ?? "/api/audio/spectrum");
        const data = await r.json();
        this.preset = data.preset ?? "flat";
        this.enabled = data.enabled !== false;
        drawFakeSpectrum(canvas, data.bands ?? []);
      } catch {
        drawFakeSpectrum(canvas, []);
      }
    },

    async setPreset(preset) {
      await fetch(opts.eqUrl ?? "/api/audio/eq", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset }),
      });
      this.preset = preset;
      await this.refresh();
    },
  };
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", () => {
    if (typeof Alpine !== "undefined") {
      Alpine.data("eqPanel", eqPanelFactory);
    }
  });
}
