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

apps/
  maya-gateway/     FastAPI gateway (parse → validate → call service → return)
  discord-shim/     HTTP glue between Discord and Maya (zero decision-making)

infra/
  docker-compose.dev.yml   Postgres + gateway for local dev
```

## Quick Start

```bash
cd ~/Workspace-public
uv sync
uv run maya-gateway
```

Or with Docker:

```bash
cd infra
docker compose -f docker-compose.dev.yml up
```

## Health Endpoint

```bash
curl http://localhost:8080/api/status/health
```

## Arena Endpoints

```bash
# Add a candidate
curl -X POST http://localhost:8080/api/arena/candidates \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "provider": "fal", "voice_id": "test-1"}'

# List candidates
curl http://localhost:8080/api/arena/candidates

# Create a battle
curl -X POST http://localhost:8080/api/arena/battles \
  -H "Content-Type: application/json" \
  -d '{"candidate_a_id": "<id>", "candidate_b_id": "<id>", "prompt": "battle prompt"}'

# Vote
curl -X POST http://localhost:8080/api/arena/battles/<id>/vote \
  -H "Content-Type: application/json" \
  -d '{"choice": "a"}'
```

## Notes

- Default branch is `main`.
- No sensitive data, private assets, or character content lives in this repo.
