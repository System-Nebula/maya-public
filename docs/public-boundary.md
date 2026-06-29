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

## Voice assistant

Public ships voice/assistant **contracts** in `maya-contracts`, the **turn-loop reference**
in `packages/maya-voice`, and **fake-provider benchmarks** via `make voice-eval`.

Realtime audio (Discord VC PCM in, streaming TTS out, STT gateway) integrates in
private `~/Workspace` first. Do not add GPU/CUDA credentials or homelab URLs here.

LLM runtime profiles (`LLM_PROVIDER=lmstudio|vllm|openai|fake`) are env-var only —
no provider-specific code forks in public packages.

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

