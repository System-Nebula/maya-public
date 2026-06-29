# maya-public

Public-facing Maya services — sovereign local-first assistant (Siri/Alexa-style):
arena battles, feed contracts, image generation, research agent, and voice contracts.

## Structure

```
packages/
  maya-contracts/   Pydantic schemas (source of truth for all APIs)
  maya-llm/           Provider-pluggable LLM client (lmstudio | vllm | openai | fake)
  maya-voice/         Voice turn loop + benchmark eval harness
  arena-core/         ELO math and battle logic
  maya-db/            Postgres connection, base models, migrations
  maya-image/         ComfyUI image service + imagine API (maya_image.api)
  maya-research/      LangGraph research agent
  ...

apps/
  maya-gateway/     FastAPI gateway (parse → validate → call service → return)
  maya-bot/           Discord bot — `/imagine` ComfyUI arena
  discord-shim/       HTTP glue between Discord and Maya
```

## Quick Start

```bash
cd ~/Workspace-public
cp .env.example .env
uv sync --all-packages
uv run maya-gateway
```

## Validation

```bash
uv sync --all-packages
make test              # all Python unit suites
make typecheck         # pyright on contracts + llm + voice
make voice-eval        # fake-provider voice latency benchmarks
make e2e-test          # Playwright (DB-free specs first)
```

## LLM provider profiles

Set `LLM_PROVIDER` to switch runtimes without code changes:

| Profile | Use |
|---------|-----|
| `lmstudio` | Jovan's Windows + LM Studio dev lane (`localhost:1234/v1`) |
| `vllm` | Linux/Nix production Ornith/vLLM |
| `openai` | OpenAI-compatible cloud API |
| `fake` | CI / unit tests |

Optional overrides: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_ENABLED`.

## Voice assistant boundary

Public repo ships **contracts** (`maya-contracts` voice/assistant models), **eval harness**
(`make voice-eval`), and the **turn-loop reference** (`packages/maya-voice`). Realtime audio
runtime (Discord VC, STT gateway, streaming TTS into VC) integrates in private `~/Workspace`
first. See `docs/public-boundary.md`.

The gateway boots without a database — `/`, `/docs`, and `/api/status/*` work
immediately. Endpoints that read/write data (arena, feeds, follow, …) need
Postgres; set `DATABASE_URL` in `.env` to point at one.

`uv run maya-ingest` runs the feed/ingest worker (also reads `.env`).

### Discord bot + image arena

See [`apps/maya-bot/README.md`](apps/maya-bot/README.md) for clone-and-run setup:
Postgres migrations → ComfyUI on `:3000` → `uv run maya-bot` → `/imagine mode:Arena`.

## Health & docs

```bash
curl http://localhost:8090/api/status/health   # liveness
curl http://localhost:8090/api/status/ready     # readiness (reports DB state)
# Interactive API docs: http://localhost:8090/docs
```

## Arena Endpoints

```bash
# Add a candidate
curl -X POST http://localhost:8090/api/arena/candidates \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "provider": "fal", "voice_id": "test-1"}'

# List candidates
curl http://localhost:8090/api/arena/candidates

# Create a battle
curl -X POST http://localhost:8090/api/arena/battles \
  -H "Content-Type: application/json" \
  -d '{"candidate_a_id": "<id>", "candidate_b_id": "<id>", "prompt": "battle prompt"}'

# Vote
curl -X POST http://localhost:8090/api/arena/battles/<id>/vote \
  -H "Content-Type: application/json" \
  -d '{"choice": "a"}'
```

## Notes

- Default branch is `main`.
- No sensitive data, private assets, or character content lives in this repo.
