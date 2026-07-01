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
- Gateway suite: `make gateway-test` (needs migrated Postgres for inbox webhook).
- Image tests: `uv run --project packages/maya-image --with pytest pytest packages/maya-image/tests/`
- CI: `.github/workflows/test.yml` — Postgres 16 + pgvector, migrations, full pytest matrix.
- `uv run --project packages/maya-research --with pytest --with pytest-asyncio pytest packages/maya-research/tests/` → all pass.

### Postgres (optional, for data-backed flows)

- NOT installed by the update script (system dependency). To enable data flows
  install `postgresql-16` + `postgresql-16-pgvector`, start the cluster, and
  create DB `maya_public` (user `postgres`/`postgres`) with extensions
  `uuid-ossp` and `vector`. `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/maya_public`.
- The pgvector extension **is required** by several Alembic migrations
  (`CREATE EXTENSION vector`).

### Resolved in this branch

- **Arena migration + ORM FK types** — UUID columns throughout; `uuid-ossp` enabled in init migration.
- **Ideogram4 graph tests** — repo-root workflow path with inline fallback.
- **Arena unit tests** — `conftest.py` skips on-disk Comfy weight checks.
- **maya-audio** — VAD bypass limited to streaming fake backend; slugify collapses hyphens.
- **CI** — Postgres + pgvector service, full migrations, gateway/contracts/llm/audio/image tests.

### Remaining notes

- Arena integration tests without local Postgres retry slowly (~3 min); CI stays fast with the service container.

### Other services (not exercised here)

- `apps/maya-bot` (Discord `/imagine` arena) needs `DISCORD_TOKEN`, Postgres
  migrations, and a ComfyUI/GPU stack — see `apps/maya-bot/README.md`.
- `apps/maya-ingest` (Prefect feed/research worker) — see `Makefile` `ingest-*`.
