# Maya Gateway

Thin public-safe FastAPI gateway with a Hyprland-inspired start-page frontend.

## Endpoints

| Path | Description |
|------|-------------|
| `/` | Start-page SPA (hyprstart) |
| `/docs` | Swagger UI (auto-generated) |
| `/redoc` | ReDoc docs |
| `/api/status/health` | Health check |
| `/api/status/ready` | Readiness probe |
| `/api/arena/*` | Arena battle endpoints |
| `/api/registry/*` | Model registry endpoints |

| `/api/auth/*` | Registration, login, session, connections |
| `/auth/google` | Google OAuth (register / login / connect) |
| `/gateway/connectors/discord/*` | Discord link + verified role |

## Authentication

Invite-gated email/password registration plus Google and Discord SSO. When `AUTH_DISABLED=1` (default), routes use `operator_id=local` without login.

### Enable auth

1. Copy `.env.example` to `.env` (gitignored) and set `AUTH_DISABLED=0`, `SESSION_SECRET`, and `ENV=development`.
2. Run migrations: `uv run alembic -c packages/maya-db/alembic.ini upgrade head`
3. Seed dev users and invite code:

   ```bash
   make auth-seed MAYA_SEED_WARBY_PASSWORD=dev MAYA_SEED_ADMIN_PASSWORD=dev
   # or one shared password:
   make auth-seed MAYA_SEED_DEV_PASSWORD=dev
   ```

   Creates invite `dev-invite`, `warby@localhost`, and `admin@localhost` (idempotent).

4. Wire OAuth credentials (local only — do not commit secrets):

   | Provider | Copy from | Notes |
   |----------|-----------|-------|
   | Google | `~/Workspace/start-page/.env` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
   | Discord app ID | `~/Workspace/.env` | `DISCORD_CLIENT_ID` (same as `DISCORD_APPLICATION_ID`) |
   | Discord secret | [Discord Developer Portal](https://discord.com/developers/applications) → OAuth2 | Paste into `DISCORD_CLIENT_SECRET` (empty in repo) |

   Example gateway `.env` fragment:

   ```bash
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8090/auth/google/callback
   DISCORD_REDIRECT_URI=http://127.0.0.1:8090/gateway/connectors/discord/callback
   MAYA_GATEWAY_URL=http://127.0.0.1:8090
   ```

5. Add matching redirect URIs in each provider console (Google Cloud Console and Discord Developer Portal).

### SSO flows

| Flow | Google | Discord |
|------|--------|---------|
| Login (existing linked account) | `/auth/google?intent=login` | `/auth/discord?intent=login` |
| Register (invite required) | `/auth/google?intent=register&invite_code=…` | `/auth/discord?intent=register&invite_code=…` |
| Link account (logged in) | `/auth/google?intent=connect` | `/gateway/connectors/discord/start` |

The auth gate shows Google and Discord buttons only when each provider is configured (`google_configured` / `discord_configured` on `/api/auth/me`). Misconfigured providers redirect to `/?auth_error=…` instead of a dead-end.

### Verified Discord role

Set `DISCORD_GUILD_ID`, `DISCORD_VERIFIED_ROLE_ID`, and reuse `DISCORD_TOKEN` (bot needs Manage Roles; role below bot role). Linking Discord from **Accounts & Integrations** grants the verified role.

### Bot linking

Set `MAYA_PUBLIC_URL=http://localhost:8090` and `IMAGINE_SKIP_PORTAL_LINK=0`. Users register with invite code, connect Discord in **Accounts & Integrations**, then `/imagine` resolves via linked identity.

## Frontend

The root path (`/`) serves the built `hyprstart` SPA — a dark, Hyprland-themed desktop start page with workspaces, a window manager, terminal, quick links, weather, and more.

Static assets live in `src/maya_gateway/static/` (copied from the `start-page` build output).

### UI stacks

| Path | Stack |
|------|-------|
| `/` | React hyprstart SPA + Alpine `micInput` islands (`alpine.min.js`, `dictation-sdk.js`) |
| `/gateway/imagine` | Alpine.js full page |
| `/static/gateway/audio/*` | Voice SDK (`micInput`, `eqPanel`) |

Voice widgets use the **Alpine gateway pattern** (same as Imagine), not a React bridge.
Preact is a possible future hyprstart shell migration; voice stays on gateway static JS.

### Rebuild the frontend

```bash
cd ../../Workspace/start-page
npm install
npm run build
cp -r dist/* ../Workspace-public/apps/maya-gateway/src/maya_gateway/static/
```

Or via Nix:

```bash
cd ../../Workspace/start-page
nix build
# Result symlink contains the built static files
cp -r result/* ../Workspace-public/apps/maya-gateway/src/maya_gateway/static/
```

## Run

```bash
uv run maya-gateway
```

Or with Docker:

```bash
docker build -t maya-gateway .
docker run -p 8080:8080 maya-gateway
```
