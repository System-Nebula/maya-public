# maya-public

Public-facing Maya services — arena battles, feed contracts, and image generation APIs.

## Structure

```
packages/
  maya-contracts/   Pydantic schemas (source of truth for all APIs)
  arena-core/       ELO math and battle logic
  fal-client/       Normalized fal.ai async client
  obs-client/       Observability / structured logging
  maya-db/          Postgres connection, base models, migrations
  maya-image/       ComfyUI image service + arena orchestration
  maya-feeds/       Creator-intel feed pipeline
  maya-graph/       Graph helpers (follow / discovery)
  maya-research/    Release-diff + research helpers

apps/
  maya-gateway/     FastAPI gateway (parse → validate → call service → return)
  maya-bot/         Discord bot — `/imagine` ComfyUI arena (self-hostable)
  discord-shim/     HTTP glue between Discord and Maya (zero decision-making)

infra/
  comfyui/          ComfyUI workflow JSON, weight fetch scripts, compose template
  docker-compose.dev.yml   Dev gateway over the shared `dev` Postgres network
```

## Quick Start

```bash
cd ~/Workspace-public
cp .env.example .env          # then edit; gateway listens on PORT (default 8090)
uv sync --all-packages        # --all-packages installs the apps, not just the root
uv run maya-gateway
```

The gateway boots without a database — `/`, `/docs`, and `/api/status/*` work
immediately. Endpoints that read/write data (arena, feeds, follow, …) need
Postgres; set `DATABASE_URL` in `.env` to point at one.

`uv run maya-ingest` runs the feed/ingest worker (also reads `.env`).

### Reproducible dev shell (Nix)

`flake.nix` pins the full dev toolchain (Python 3.11, `uv`, PostgreSQL 16 +
pgvector, `bun`, Node, and the Playwright browsers) so dev builds reproduce
exactly across machines:

```bash
nix develop            # enters the pinned shell (or `direnv allow` with .envrc → `use flake`)
uv sync --all-packages
ENV=development PORT=8090 uv run maya-gateway
```

Inside the shell, `PLAYWRIGHT_BROWSERS_PATH` is pre-set, so `make e2e-test`
(and `bun x playwright test`) run without the ad-hoc `nix-shell -p` calls.

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
