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
