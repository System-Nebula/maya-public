# AGENTS.md

## Cursor Cloud specific instructions

This is a Python **uv workspace** monorepo (`pyproject.toml` → `[tool.uv.workspace]`,
members under `packages/*` and `apps/*`). The flagship runnable service is the
FastAPI **`maya-gateway`**. `uv` is installed at `~/.local/bin` and is on the login
`PATH`; the startup update script runs `uv sync --all-packages`.

### Running the gateway (primary app)

- Dev mode (hot reload): `ENV=development PORT=8090 uv run maya-gateway`
  (or `make gateway-dev`). It listens on `PORT`, default `8090`.
- The gateway **boots without a database** — `/`, `/docs`, `/redoc`,
  `/api/status/health`, and many parse/resolve endpoints (e.g.
  `POST /api/follow/resolve`) work immediately. Endpoints that read/write data
  (arena, feeds, follow tree, discover inbox, research) need Postgres via
  `DATABASE_URL`.
- A prebuilt homepage SPA is committed in
  `apps/maya-gateway/src/maya_gateway/static/` and served at `/`. The SPA source
  (`apps/homepage`) is gitignored and lives in a separate repo, so `make
  homepage-*` / `bun` targets are not runnable from this repo alone.

### Tests / lint

- Commands are documented in the `Makefile` (`gateway-test`, `research-test`,
  etc.). There is no separate lint step configured in CI for the Python side.
- Gateway suite: `uv run --project apps/maya-gateway --with pytest pytest apps/maya-gateway/tests/`
  — 64/65 pass without setup. The one failure (`test_discover_inbox_webhook`)
  needs Postgres tables (see known issues below).
- `uv run --project packages/maya-research --with pytest --with pytest-asyncio pytest packages/maya-research/tests/` → all pass.

### Postgres (optional, for data-backed flows)

- NOT installed by the update script (system dependency). To enable data flows
  install `postgresql-16` + `postgresql-16-pgvector`, start the cluster, and
  create DB `maya_public` (user `postgres`/`postgres`) with extensions
  `uuid-ossp` and `vector`. `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/maya_public`.
- The pgvector extension **is required** by several Alembic migrations
  (`CREATE EXTENSION vector`).

### Known pre-existing issues (not environment problems)

- **Alembic migrations fail on a fresh DB.** The initial migration
  `packages/maya-db/migrations/versions/a511a30e9f86_init_arena_tables.py`
  declares `arena_battles.candidate_a_id`/`candidate_b_id` as `VARCHAR(36)` with
  a foreign key to `arena_candidates.id`, which is `UUID` — Postgres rejects the
  FK ("incompatible types: character varying and uuid"). The same mismatch
  exists in the ORM model (`packages/maya-db/src/maya_db/models/arena.py`). This
  blocks `alembic upgrade head` and therefore all DB-backed gateway/bot flows
  and `test_discover_inbox_webhook`.
- **maya-image tests (8) fail** because the workflow JSON fixtures they read
  (e.g. `packages/maya-image/infra/comfyui/workflows/ideogram4/...`, resolved
  from `comfy_graphs.py` `parents[2]/infra/...`) are not committed; the only
  committed workflows live at repo-root `infra/comfyui/workflows/{zimage,krea2}`.

### Other services (not exercised here)

- `apps/maya-bot` (Discord `/imagine` arena) needs `DISCORD_TOKEN`, Postgres
  migrations, and a ComfyUI/GPU stack — see `apps/maya-bot/README.md`.
- `apps/maya-ingest` (Prefect feed/research worker) — see `Makefile` `ingest-*`.
