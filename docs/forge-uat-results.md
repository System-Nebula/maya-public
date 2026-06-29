# Forge Imagine UAT Results

Run date: 2026-06-28  
Commit: `b42e5d3` (+ Forge UAT changes on branch)  
Environment: `MAYA_FAKE_COMFY=1`, DB-free in-memory arena cache

## Commands

```bash
make forge-uat-smoke          # gateway unit tests
make forge-uat-e2e            # Playwright browser UAT (NixOS: nix-shell -p bun nodejs playwright-driver.browsers)
```

Real Comfy/GPU acceptance (manual, not run in CI):

```bash
unset MAYA_FAKE_COMFY
export COMFYUI_API_URL=http://localhost:3000
export HF_TOKEN=...
export MAYA_IMAGE_ROOT=./data/outputs/maya-image
uv run maya-gateway
# open http://localhost:8090/gateway/imagine — prompts: neon rooftop, a cat
```

## Pass / fail matrix

| Scenario | DB-free smoke | Browser UAT | Notes |
|----------|---------------|-------------|-------|
| Open page (composer, feed, leaderboard shell) | pass | pass | `GET /gateway/imagine` |
| Generate (`neon rooftop`) | pass | pass | fake Comfy placeholder PNGs |
| Progress (SSE / poll) | pass | pass | poll fallback test blocks SSE |
| Ready → voting | pass | pass | both slots have URLs |
| Vote → resolved | pass | pass | models revealed after vote |
| Leaderboard refresh | pass | pass | post-vote fetch |
| Error card on provider failure | n/a | manual | requires Comfy outage or injected failure |
| Discord/web parity (`complete_battle`) | code | manual | Discord cog updated; verify in bot |
| Real Comfy Z-Image vs Krea 2 | manual | manual | GPU + weights required |

## Automated evidence (2026-06-28)

- `apps/maya-gateway/tests/test_imagine_routes.py`: **7 passed**
- `tests/e2e/tests/gateway-imagine.spec.ts` + `forge-imagine-uat.spec.ts`: **6 passed**

No generated PNGs, Discord IDs, or private journal data are stored in this repo.
E2E artifacts: `tests/e2e/.artifacts/` (gitignored).

## Known gaps

- Real ComfyUI/GPU acceptance run is operator-verified only.
- Provider failure UI regression is not automated (fake provider always succeeds).
- Homepage launcher link to `/gateway/imagine` is optional follow-up.
