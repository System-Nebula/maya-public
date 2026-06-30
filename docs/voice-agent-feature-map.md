# Voice-agent feature map

Durable checklist mapping the Jovan voice-agent demo (`packages/maya-voice-stack/static/`)
to Maya packages and delivery phases. Pass 1 ships **search-bar dictation** only; the full
agent surface is phase 2+.

Design reference: `packages/maya-voice-stack/static/index.html`, `eq-ui.js`, and the
benchmark harness in `packages/maya-voice-stack/`.

## Shared state vocabulary

All surfaces align on `VoiceTurnState` (`maya-contracts/voice.py`) and Jovan `STATUS_LABEL`:

`loading` → `listening` → `hearing` → `transcribing` → `thinking` → `speaking` → `idle` | `error`

| Surface | States used |
|---------|-------------|
| Search-bar dictation (pass 1) | `idle` → `listening` → `hearing` → `transcribing` → `idle` |
| Full voice agent (phase 2) | Full loop including `thinking`, `speaking`, barge-in |

---

## UI pages (Jovan sidebar)

| Page | Jovan icons | Features | Maya phase | Acceptance |
|------|-------------|----------|------------|------------|
| **Home / Talk** | Home | Hero mic, status pill, hint, output EQ card, conversation log | Mic → **pass 1** (`micInput` in hyprstart); EQ stub → **pass 1**; log → phase 2 | Pass 1: mic in search pill writes transcript; EQ renders fake spectrum |
| **Voice** | Mic | Voice select, upload, preview, speaker list | Phase 2 | `GET /voices`, upload + select routes; preview WAV plays |
| **Avatar** | User | VTS enable, auto-express, emotion→action map, connection badge | Phase 3 (`maya-scene` / private VTS) | VTS WebSocket connected; test expression fires |
| **Settings** | Gear | System prompt, delivery, barge-in, auto-instruct, xvec-only, voice description | Phase 2 | `GET/POST /config` round-trip; TurnLoop reads config |

---

## Backend capabilities

| Capability | Jovan API | Owner package | Phase | Pass 1 status |
|------------|-----------|---------------|-------|---------------|
| ASR stream | browser mic → WS | `maya-audio` `WS /api/audio/stream` | **Pass 1** | Fake partial/final transcripts |
| TTS stream | agent internal | `maya-audio` TTS backend | Phase 2 GPU | `fake-tts` stub only |
| LLM stream | OpenAI-compat | `maya-llm` | Exists | — |
| Turn loop | VoiceAgent | `maya-voice` TurnLoop | Phase 2 | Injectable STT stub |
| Output EQ | player biquads + `/spectrum` | `maya-audio/tts/eq.py` + `EqProcessor` | **Stub pass 1**, GPU phase 2 | `FakeEqProcessor`; `GET /api/audio/spectrum`, `POST /api/audio/eq` |
| Voice clone | `/voices`, `/upload-voice`, `/select-voice` | `maya-audio` + gateway | Phase 2 | Not started |
| VTS | `/vts-status`, `/vts-map`, `/vts-test` | private / `maya-scene` | Phase 3 | Not started |
| Config | `GET/POST /config` | gateway + contracts | Phase 2 | Not started |
| Session | `POST /start`, `/stop` | browser dictation vs full agent | Split | Dictation = browser `getUserMedia`; no server mic |
| Events | `GET /events` SSE | `VoiceEvent` contract stream | Phase 2 voice app | Benchmark harness only |
| Benchmark | `POST /benchmark/turn` | `maya-voice-stack` | Exists | WAV replay regression |

---

## Pass 1 deliverables (this PR)

### micInput SDK

| Asset | Path | Role |
|-------|------|------|
| Dictation core | `apps/maya-gateway/.../dictation-sdk.js` | `Dictation`, `micInput`, `bindMicInput`, Jovan mic SVG |
| Styles | `dictation-sdk.css` | Pulse keyframes, state classes |
| Worklet | `resample-worklet.js` | PCM16 @ 16 kHz for WS |

**Wiring:** `apps/homepage` → `MicInputIsland` (Alpine `micInput` + `Alpine.initTree`) in
`DesktopWidgets.tsx` and `Launcher.tsx`. `index.html` loads `alpine.min.js` + `dictation-sdk.js`.
`data-testid`: `desktop-search-mic`, `desktop-search-input`, `launcher-mic`, `launcher-input`.

### Gateway UI stacks

| Surface | Stack | Notes |
|---------|-------|-------|
| `/` hyprstart | React + Alpine islands | Desktop shell is React; voice mic uses Alpine `micInput` |
| `/gateway/imagine` | Alpine full page | Same pattern as future `/gateway/voice` |
| Preact (future) | Optional hyprstart rewrite | Frankie suggestion; does not block Alpine voice widgets |

**Do not ship:** standalone `dictation-demo.html`; server-side `sounddevice` mic for web dictation.

### EQ stub (output chain)

EQ is a **TTS output-chain operator**, not part of ASR/dictation.

```python
# packages/maya-audio/src/maya_audio/tts/eq.py
class EqProcessor(Protocol):
    def apply(self, pcm, sample_rate) -> pcm: ...
    def spectrum(self, n_bands=56) -> list[dict]: ...
    def set_preset(self, preset: str) -> None: ...
    def set_bands(self, bands: list) -> None: ...
```

| Asset | Path | Role |
|-------|------|------|
| Protocol + fake | `maya-audio/tts/eq.py` | `FakeEqProcessor` for tests |
| Alpine shell | `eq-panel.js`, `eq-panel.css` | Canvas + presets against fake spectrum |
| Gateway stubs | `GET /api/audio/spectrum`, `POST /api/audio/eq` | No-op until GPU playback |

---

## Media pipeline placement

```
MicInput (browser) ──► StreamSession (ASR) ──► TurnLoop / search input
TTS Backend ──► EqProcessor ──► PlaybackSink
EqProcessor.spectrum ──► eqPanel (UI)
```

EQ and conversation log stay **off** the startpage. Full agent mounts at `/gateway/voice` (phase 2).

---

## Phase 2 roadmap

| Deliverable | Description |
|-------------|-------------|
| `/gateway/voice` | Jovan Home: hero mic, live `eqPanel`, conversation log, SSE `VoiceEvent` |
| Voice + Settings pages | Clone upload, config POST, delivery/barge-in |
| GPU path | `maya-voice-stack` demo behind `[demo]` imports real `maya-audio` backends; EQ binds biquads |
| hyprstart window | Optional `openApp('voice')` embedding `/gateway/voice` iframe |

---

## Phase 3 roadmap

| Deliverable | Description |
|-------------|-------------|
| Avatar / VTS | Emotion map via `maya-scene` boundary |
| Live Discord PCM | `discord-shim` → gateway stream session |

---

## Verification

| Check | Command / test |
|-------|----------------|
| Gateway audio routes | `pytest apps/maya-gateway/tests/test_audio_routes.py` |
| EqProcessor contract | `pytest packages/maya-audio/tests/test_eq_fake.py` |
| Startpage mic e2e | Playwright `mic-search.spec.ts` (mock getUserMedia + WS) |
| Deployed startpage | `make homepage-deploy`; gateway at `:8090` shows mic in search pill |
