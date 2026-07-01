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
- Gateway suite: `make gateway-test` or
  `uv run --project apps/maya-gateway --with pytest pytest apps/maya-gateway/tests/`
  — most pass without Postgres. `test_discover_inbox_webhook` needs a migrated DB.
- Image tests: `uv run --project packages/maya-image --with pytest pytest packages/maya-image/tests/`
- CI: `.github/workflows/test.yml` runs gateway, maya-image, and maya-research on push/PR.
- `uv run --project packages/maya-research --with pytest --with pytest-asyncio pytest packages/maya-research/tests/` → all pass.

### Postgres (optional, for data-backed flows)

- NOT installed by the update script (system dependency). To enable data flows
  install `postgresql-16` + `postgresql-16-pgvector`, start the cluster, and
  create DB `maya_public` (user `postgres`/`postgres`) with extensions
  `uuid-ossp` and `vector`. `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/maya_public`.
- The pgvector extension **is required** by several Alembic migrations
  (`CREATE EXTENSION vector`).

### Resolved on `fix/main-dev-blockers` (pending merge to main)

- **Arena migration FK types** — `arena_battles.candidate_*_id` and `winner_id` are
  now `UUID`, matching `arena_candidates.id`.
- **Ideogram4 graph tests** — `create_ideogram4_graph()` resolves the workflow
  from repo-root `infra/comfyui/workflows/ideogram4/` with an inline fallback when
  the Comfy export is not checked in.

### Remaining known issues

- **Some maya-image arena tests** reference `maya_image.db` modules that are not
  in the public tree; `test_comfy_bind.test_inject_prompt_and_dimensions` expects
  z-image node IDs from the JSON template, not the programmatic graph.

### Other services (not exercised here)

- `apps/maya-bot` (Discord `/imagine` arena) needs `DISCORD_TOKEN`, Postgres
  migrations, and a ComfyUI/GPU stack — see `apps/maya-bot/README.md`.
- `apps/maya-ingest` (Prefect feed/research worker) — see `Makefile` `ingest-*`.
