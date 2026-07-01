// dictation-sdk.js — browser mic → /api/audio/stream → transcript into any input.
// Core Alpine component: micInput. Imperative bind: bindMicInput (for React hyprstart).

export const MIC_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;

export const STATUS_LABEL = {
  idle: "",
  listening: "Listening…",
  hearing: "Hearing you…",
  transcribing: "Transcribing…",
  error: "Error",
};

export function streamWsUrl(path = "/api/audio/stream") {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

function workletModuleUrl() {
  try {
    return new URL("resample-worklet.js", import.meta.url).href;
  } catch {
    return "/static/gateway/audio/resample-worklet.js";
  }
}

/** React/HTMX-safe: set input value and notify listeners. */
export function writeInputValue(input, text) {
  if (!input) return;
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  if (setter) setter.call(input, text);
  else input.value = text;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(
    new CustomEvent("maya:dictation", { detail: text, bubbles: true }),
  );
}

function applyMicClasses(button, status) {
  button.classList.remove(
    "mic-input-btn--active",
    "mic-input-btn--listening",
    "mic-input-btn--hearing",
    "mic-input-btn--transcribing",
  );
  if (status === "listening") button.classList.add("mic-input-btn--listening", "mic-input-btn--active");
  else if (status === "hearing") button.classList.add("mic-input-btn--hearing", "mic-input-btn--active");
  else if (status === "transcribing") button.classList.add("mic-input-btn--transcribing", "mic-input-btn--active");
  else if (status === "error") button.classList.add("mic-input-btn--active");
}

export class Dictation {
  constructor({ url, sampleRate = 16000 } = {}) {
    this.url = url ?? streamWsUrl();
    this.sampleRate = sampleRate;
    this.ws = null;
    this.ctx = null;
    this.node = null;
    this.sink = null;
    this.stream = null;
    this.onEvent = () => {};
    // Diagnostics: how much audio actually left the browser. 0 frames = capture/worklet
    // broken; >0 frames but no events = a backend/VAD issue. onFrame is an optional hook.
    this.framesSent = 0;
    this.bytesSent = 0;
    this.onFrame = () => {};
  }

  async start() {
    this.ws = new WebSocket(this.url);
    this.ws.binaryType = "arraybuffer";
    this.ws.onmessage = (m) => {
      try {
        this.onEvent(JSON.parse(m.data));
      } catch {
        /* ignore non-JSON */
      }
    };
    await new Promise((res, rej) => {
      this.ws.onopen = res;
      this.ws.onerror = rej;
    });

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.ctx = new AudioContext({ sampleRate: this.sampleRate });
    if (this.ctx.state === "suspended") await this.ctx.resume();
    await this.ctx.audioWorklet.addModule(workletModuleUrl());
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm16-resampler");
    this.node.port.onmessage = (e) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(e.data);
        this.framesSent += 1;
        this.bytesSent += e.data.byteLength ?? 0;
        this.onFrame(e.data.byteLength ?? 0);
      }
    };
    src.connect(this.node);
    // The worklet's output must be pulled by the render graph or process() never
    // fires. Route it through a muted gain node so frames flow without echoing the
    // mic back to the speakers.
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    this.node.connect(this.sink).connect(this.ctx.destination);
  }

  stop() {
    this.node?.disconnect();
    this.sink?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    const ws = this.ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Ask the server to finalize, then close after the final event has had time to arrive
      // (delivered via onmessage → onEvent). Closing immediately would drop a non-streaming
      // backend's transcript, which is only emitted on stop/pause.
      try {
        ws.send(JSON.stringify({ type: "stop" }));
      } catch {
        /* socket already gone */
      }
      setTimeout(() => {
        try {
          ws.close();
        } catch {
          /* already closed */
        }
      }, 1000);
    } else {
      ws?.close();
    }
    this.node = null;
    this.sink = null;
    this.stream = null;
    this.ctx = null;
    this.ws = null;
  }
}

/**
 * Imperative mic bind for React (hyprstart). Returns { stop, destroy }.
 */
export function bindMicInput({
  button,
  input,
  onText,
  onStatus,
  stopOnFinal = false,
  url,
}) {
  let dictation = null;
  let listening = false;

  function setStatus(status) {
    applyMicClasses(button, status);
    button.setAttribute(
      "aria-label",
      listening ? "Stop" : "Start talking",
    );
    onStatus?.(status, STATUS_LABEL[status] ?? status);
  }

  async function start() {
    try {
      dictation = new Dictation({ url });
      dictation.onEvent = (ev) => {
        const text = ev.text ?? "";
        if (ev.is_final) {
          setStatus("transcribing");
          onText?.(text);
          writeInputValue(input, text);
          if (stopOnFinal) stop();
          else setStatus("hearing");
        } else {
          setStatus("hearing");
          onText?.(text);
          writeInputValue(input, text);
        }
      };
      setStatus("listening");
      await dictation.start();
      listening = true;
      setStatus("hearing");
    } catch (err) {
      setStatus("error");
      onStatus?.("error", String(err));
      stop();
    }
  }

  function stop() {
    listening = false;
    dictation?.stop();
    dictation = null;
    setStatus("idle");
  }

  const onClick = () => (listening ? stop() : start());
  button.addEventListener("click", onClick);
  setStatus("idle");

  return {
    stop,
    destroy() {
      stop();
      button.removeEventListener("click", onClick);
    },
  };
}

/** Inject Jovan mic icon into a button if empty. */
export function mountMicButton(button) {
  if (!button.querySelector("svg")) button.innerHTML = MIC_SVG;
  button.classList.add("mic-input-btn");
  button.type = "button";
  button.setAttribute("aria-label", "Start talking");
}

export function micInputFactory(opts = {}) {
  return {
    listening: false,
    status: "idle",
    statusLabel: "",
    error: null,
    _bind: null,

    init() {
      const input =
        opts.target
          ? document.querySelector(opts.target)
          : this.$refs?.target;
      const button = this.$refs?.micBtn;
      if (!input || !button) return;
      mountMicButton(button);
      this._bind = bindMicInput({
        button,
        input,
        url: opts.url,
        stopOnFinal: opts.stopOnFinal ?? false,
        onText: (text) => {
          if (opts.onText) opts.onText(text);
        },
        onStatus: (status, label) => {
          this.status = status;
          this.statusLabel = label;
          this.listening =
            status === "listening" || status === "hearing" || status === "transcribing";
        },
      });
    },

    toggle() {
      this.$refs?.micBtn?.click();
    },

    destroy() {
      this._bind?.destroy();
    },
  };
}

if (typeof document !== "undefined") {
  document.addEventListener("alpine:init", () => {
    if (typeof Alpine !== "undefined") {
      Alpine.data("micInput", micInputFactory);
    }
  });
}
