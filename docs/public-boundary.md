# Public Boundary

This repository is limited to generic contracts, small helper packages, and
demo-safe application scaffolding.

Do not add:

- private source mappings
- collector watch configuration
- credentials or local service URLs
- generated media or datasets
- internal operations notes

## Research agent

The research bounded context is public upstream. Extension points
(`OperatorHistoryReader`, `ResearchProgressPublisher`) ship with null implementations
here; Discord UX and Firefox history wiring live in internal `~/Workspace`.

Handoff instructions: [research-internal-handoff.md](research-internal-handoff.md)

## Audio domain (voice / ASR / TTS)

Public summary: [maya-audio-domain-summary.md](maya-audio-domain-summary.md). Detailed steering
spec: `Vault/quartz-site/content/maya-architecture/maya-audio-domain.md`.

Public ships the **audio bounded context** `packages/maya-audio` (ASR/TTS backends, realtime
stream sessions, batch jobs) behind a DRY backend layer, plus voice/assistant **contracts** in
`maya-contracts`, the **turn-loop reference** in `packages/maya-voice`, **fake-provider
benchmarks** via `make voice-eval`, and the **vendored GPU stack** in `packages/maya-voice-stack`
(Jovan's voice-agent demo) with WAV replay benchmarks, OTEL/Langfuse tracing, and Playwright web
transfer tests.

**Realtime now builds in public** (revised 2026-06-29): the realtime stream plane (gateway
dictation `/api/audio/stream`, Discord VC boundary) lands here behind **fake backends** — CI runs
zero-CUDA. The earlier "Discord VC integrates in private `~/Workspace` first" rule is retired; what
stays private is **secrets and GPU coupling, not the code**. Do not add GPU/CUDA credentials,
homelab URLs, model weights, or private Discord logs. Real GPU inference backends ship behind the
`[gpu]` extra; full-stack voice tests run on self-hosted GPU with `OPENROUTER_API_KEY` /
`VA_LLM_API_KEY` via env vars only.

## Forge imagine UAT

The Forge web UX lives at `GET /gateway/imagine` (Alpine + `/static/gateway/*`).
JSON arena routes are under `/gateway/imagine/*`; generated artifacts are served from
`/imagine-outputs/*` when `MAYA_IMAGE_ROOT` is set.

Three UAT modes (no private Discord logs, PNGs, or vote ledgers in this repo):

| Mode | Env | Purpose |
|------|-----|---------|
| DB-free smoke | `MAYA_FAKE_COMFY=1` | CI, Playwright, instant placeholder PNGs |
| Integrated arena | `DATABASE_URL` + `MAYA_FAKE_COMFY=1` | Postgres migrations + fake Comfy |
| Real Comfy/GPU | `COMFYUI_API_URL`, `HF_TOKEN`, GPU | Manual acceptance (Z-Image vs Krea 2) |

Run: `make forge-uat-smoke` (unit + gateway), `make forge-uat-e2e` (browser).
Record manual GPU results in a local note — do not commit generated media.

Service boundary: gateway mounts routes/static; `maya_image.api` owns HTTP/SSE;
`ImageJobService` owns generation; `ArenaService` owns voting/ELO. Web and Discord
both call `complete_battle()` after a vote.

