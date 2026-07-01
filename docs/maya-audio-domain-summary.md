# Maya audio domain (public summary)

Short in-repo summary for PR reviewers. The detailed steering spec lives in the
Vault at `Vault/quartz-site/content/maya-architecture/maya-audio-domain.md`.

## Problem

Jovan's voice-agent demo (`packages/maya-voice-stack`) proved the STT→LLM→TTS GPU path,
but its web mic uses **host-side** capture (`sounddevice`). Maya needs browser and Discord
audio ingress into one ASR service, plus batch production jobs (video transcript, RSS read,
audiobook), without duplicating backend code per model.

## Bounded context

One package: **`packages/maya-audio`**. Not separate `maya-asr` / `maya-tts` packages.

| Layer | Package / app | Role |
|-------|---------------|------|
| Contracts | `maya-contracts` (`asr.py`, `audio_jobs.py`, `media.py`) | Strict schemas only |
| Audio operators | `maya-audio` | ASR/TTS backends, StreamSession, BatchJobRunner |
| Turn orchestration | `maya-voice` | STT→LLM→TTS state machine (injectable backends) |
| E2E benchmark | `maya-voice-stack` | WAV replay regression harness; demo UI behind `[demo]` extra |
| HTTP ingress | `maya-gateway` | `/api/audio/*`, dictation SDK static assets |
| Discord glue | `discord-shim` | Proxies PCM to gateway; no model policy |

## Three modes

1. **Realtime stream** — PCM chunks → partial/final transcripts (`StreamSession`)
2. **Batch job** — file/URL/text → artifact (`BatchJobRunner`, research-run lifecycle)
3. **Turn loop** — conversational agent (`maya-voice`)

## DRY backends

All ASR/TTS backends extend `BaseInferenceBackend` in `maya_audio/backends/base.py`.
ASR implements `_infer`; TTS implements `_synthesize`. Shared audio I/O lives once in
`_audio.py`. Pass 1 uses fake backends; GPU stubs raise `NotImplementedError` until the
`[gpu]` follow-on.

## Public boundary (pass 1)

Realtime builds in public behind **fake backends** — CI is zero-CUDA. Secrets, model
weights, and homelab URLs stay out of this repo. See [public-boundary.md](public-boundary.md).

## Gateway surface (stub)

| Route | Purpose |
|-------|---------|
| `GET /api/audio/models` | List fake ASR/TTS model ids |
| `WS /api/audio/stream` | Realtime dictation stream |
| `POST /api/audio/jobs` | Enqueue batch job |
| `GET /api/audio/jobs/{id}/progress` | SSE progress |
| `POST /api/audio/discord/session` | Discord VC handshake stub |
| `GET /api/audio/spectrum` | Fake EQ spectrum for `eqPanel` stub |
| `POST /api/audio/eq` | EQ preset stub (phase 2 binds real playback) |

## Browser dictation (pass 1)

Search-bar mic on hyprstart (`DesktopWidgets`, `Launcher`) uses an **Alpine `micInput` island**
inside the React shell: `index.html` loads `alpine.min.js` + `dictation-sdk.js`; React mounts
`x-data="micInput({ target: '#…' })"` hosts and calls `Alpine.initTree()` after render.

See [voice-agent-feature-map.md](voice-agent-feature-map.md) for the full Jovan → Maya phase checklist.

## Gateway UI stacks

| Surface | URL | Stack |
|---------|-----|-------|
| hyprstart desktop | `/` | React SPA + Alpine islands for voice widgets |
| Imagine | `/gateway/imagine` | Alpine.js (full page) |
| Voice SDK | `/static/gateway/audio/*` | Alpine `micInput`, `eqPanel` |
| Voice app (phase 2) | `/gateway/voice` | Alpine page (planned) |

Preact was suggested as a future lighter alternative for the hyprstart shell; voice widgets
should stay on Alpine gateway static JS regardless.

Video (`.mov`/`.mkv`), OBS livestream, and Blender MCP sit on a higher timeline abstraction
(`maya-contracts/media.py`). `maya-audio` remains an **operator** over audio tracks, not the
omni layer. Adapters (OBS, Blender MCP, demux) follow after pass 1 merges.

## Follow-on (not pass 1)

Real faster-whisper backend, Parakeet ONNX, arena A/B (`arena-core`), feedback persistence,
live Discord PCM proxy, production batch pipelines.
