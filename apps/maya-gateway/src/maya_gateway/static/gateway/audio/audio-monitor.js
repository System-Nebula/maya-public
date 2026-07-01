// audio-monitor.js — Alpine `audioMonitor`: a mic diagnostic harness.
//
// Two independent tools, both answerable at a glance:
//   1. Level meter  — client-side getUserMedia + AnalyserNode. Proves the mic actually
//      captures audio, with zero backend involved. Flat = capture broken; moving = mic OK.
//   2. Stream demo  — reuses the dictation `Dictation` class to push PCM to /api/audio/stream,
//      surfacing frames/bytes sent + raw transcript events + the active ASR backend.

import { Dictation, streamWsUrl } from "/static/gateway/audio/dictation-sdk.js";

export function audioMonitorFactory(opts = {}) {
  return {
    // backend badge
    asrModel: "…",
    backendHint: "",

    // level meter
    meterOn: false,
    level: 0, // 0..1 (rms)
    peak: 0, // 0..1
    db: -100, // dBFS
    _meterStream: null,
    _meterCtx: null,
    _analyser: null,
    _raf: null,

    // stream demo
    streamOn: false,
    framesSent: 0,
    bytesSent: 0,
    lastFinal: "",
    events: [],
    _dictation: null,
    _pollTimer: null,

    async init() {
      await this.loadBackend();
    },

    destroy() {
      this.stopMeter();
      this.stopStream();
    },

    async loadBackend() {
      try {
        const r = await fetch(opts.modelsUrl ?? "/api/audio/models");
        const data = await r.json();
        this.asrModel = data?.asr?.[0]?.id ?? "unknown";
      } catch {
        this.asrModel = "unreachable";
      }
      this.backendHint =
        this.asrModel === "fake-asr"
          ? 'fake backend — always returns "hello maya" regardless of audio. Set MAYA_ASR_BACKEND=whisper for real dictation.'
          : `real backend (${this.asrModel}) — transcribes actual speech.`;
    },

    // ---- level meter (no backend) ----
    async startMeter() {
      if (this.meterOn) return;
      try {
        this._meterStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this._meterCtx = new AudioContext();
        const src = this._meterCtx.createMediaStreamSource(this._meterStream);
        this._analyser = this._meterCtx.createAnalyser();
        this._analyser.fftSize = 1024;
        src.connect(this._analyser);
        this.meterOn = true;
        this._tick();
      } catch (err) {
        this.meterOn = false;
        this.events.unshift({ t: this._stamp(), kind: "error", text: `mic: ${err}` });
      }
    },

    _tick() {
      if (!this._analyser) return;
      const buf = new Uint8Array(this._analyser.fftSize);
      this._analyser.getByteTimeDomainData(buf);
      let sum = 0;
      let peak = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128; // -1..1
        sum += v * v;
        const a = Math.abs(v);
        if (a > peak) peak = a;
      }
      const rms = Math.sqrt(sum / buf.length);
      this.level = rms;
      this.peak = peak;
      this.db = rms > 0 ? Math.max(-100, Math.round(20 * Math.log10(rms))) : -100;
      this._raf = requestAnimationFrame(() => this._tick());
    },

    stopMeter() {
      if (this._raf) cancelAnimationFrame(this._raf);
      this._raf = null;
      this._analyser = null;
      this._meterStream?.getTracks().forEach((t) => t.stop());
      this._meterCtx?.close();
      this._meterStream = null;
      this._meterCtx = null;
      this.meterOn = false;
      this.level = 0;
      this.peak = 0;
      this.db = -100;
    },

    // ---- stream demo (full pipeline) ----
    async startStream() {
      if (this.streamOn) return;
      this.framesSent = 0;
      this.bytesSent = 0;
      this.lastFinal = "";
      this.events = [];
      this._dictation = new Dictation({ url: opts.streamUrl ?? streamWsUrl() });
      this._dictation.onEvent = (ev) => {
        const text = ev.text ?? "";
        if (ev.is_final) this.lastFinal = text;
        this.events.unshift({
          t: this._stamp(),
          kind: ev.is_final ? "final" : "partial",
          text,
        });
        if (this.events.length > 40) this.events.length = 40;
      };
      try {
        await this._dictation.start();
        this.streamOn = true;
        this.events.unshift({ t: this._stamp(), kind: "info", text: "stream connected" });
        this._pollTimer = setInterval(() => {
          this.framesSent = this._dictation?.framesSent ?? 0;
          this.bytesSent = this._dictation?.bytesSent ?? 0;
        }, 120);
      } catch (err) {
        this.streamOn = false;
        this.events.unshift({ t: this._stamp(), kind: "error", text: `stream: ${err}` });
        this._dictation = null;
      }
    },

    stopStream() {
      if (this._pollTimer) clearInterval(this._pollTimer);
      this._pollTimer = null;
      this._dictation?.stop();
      this._dictation = null;
      this.streamOn = false;
    },

    _stamp() {
      const d = new Date();
      return d.toLocaleTimeString([], { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
    },
  };
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", () => {
    if (typeof Alpine !== "undefined") {
      Alpine.data("audioMonitor", audioMonitorFactory);
    }
  });
}
