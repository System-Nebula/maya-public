# Maya public — convenience targets for the feature/maya_music branch.
#
# Most paths assume you're running from the repo root.
# JS/TS toolchain: bun (use `nix-shell -p bun` if bun isn't on PATH).

HOMEPAGE_DIR := apps/homepage
GATEWAY_STATIC := apps/maya-gateway/src/maya_gateway/static
E2E_DIR := tests/e2e

# Local services. Override on the command line if your setup differs:
#   make gateway-dev GATEWAY_PORT=9000
#   make db-create PGPORT=5432
GATEWAY_PORT ?= 8090
PGHOST ?= localhost
PGPORT ?= 5433
PGUSER ?= maya
PGPASSWORD ?= maya
PGDATABASE ?= maya_public
DATABASE_URL ?= postgresql+asyncpg://$(PGUSER):$(PGPASSWORD)@$(PGHOST):$(PGPORT)/$(PGDATABASE)

# NixOS-friendly Playwright runner: borrow the patched chromium from
# nixpkgs (playwright-driver.browsers) so we don't try to launch a generic
# Linux binary. Override on other distros if needed.
NIX_PLAYWRIGHT_PKGS ?= bun python313 uv playwright-driver.browsers
PLAYWRIGHT_BROWSERS_PATH ?= $(shell nix-shell -p playwright-driver.browsers --run 'echo $$buildInputs' 2>/dev/null | tr ' ' '\n' | grep playwright-browsers | head -1)

WORKSPACE_ROOT ?= $(HOME)/Workspace

# Real local dictation by default. Override with `make gateway-dev MAYA_ASR_BACKEND=fake`.
# numpy/ctranslate2 need libstdc++ + libz on the loader path; pull both from nixpkgs so we
# don't hardcode /nix/store hashes (which get garbage-collected).
MAYA_ASR_BACKEND ?= whisper
NUMPY_NIX_LIBS ?= $(shell nix-shell -p stdenv.cc.cc.lib zlib.out --run 'for p in $$buildInputs; do printf "%s/lib:" "$$p"; done' 2>/dev/null)

.PHONY: help homepage-deps homepage-dev homepage-build homepage-deploy \
        gateway-dev gateway-test test typecheck voice-eval voice-stack-test voice-e2e-gpu voice-benchmark voice-e2e \
        e2e-deps e2e-install e2e-test docker-build clean-homepage \
        feeds-migrate ingest-dev ingest-poll ingest-embed ingest-backfill ingest-analyze ingest-parse-intel \
        bootstrap-ukf bootstrap-misskatie \
        research-test research-flow \
        db-create db-shell slskd-ingest-fixtures slskd-worker slskd-status slskd-probe \
        slskd-export-queue slskd-batch slskd-history-ingest slskd-worker-once slskd-album-grab \
        forge-uat-smoke forge-uat-e2e forge-uat-integrated

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} /^[a-zA-Z_-]+:.*##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

homepage-deps: ## Install bun deps for the homepage SPA
	cd $(HOMEPAGE_DIR) && bun install

homepage-dev: ## Run the Vite dev server (http://localhost:5173)
	cd $(HOMEPAGE_DIR) && bun run dev

homepage-build: ## Build the homepage SPA into dist/
	cd $(HOMEPAGE_DIR) && bun run build

homepage-deploy: homepage-build ## Build and copy the SPA into the gateway static dir
	mkdir -p $(GATEWAY_STATIC)
	@tmp=$$(mktemp -d); \
	for keep in gateway demo artifacts; do \
	  if [ -d "$(GATEWAY_STATIC)/$$keep" ]; then cp -a "$(GATEWAY_STATIC)/$$keep" "$$tmp/"; fi; \
	done; \
	rm -rf $(GATEWAY_STATIC)/*; \
	cp -R $(HOMEPAGE_DIR)/dist/. $(GATEWAY_STATIC)/; \
	for keep in gateway demo artifacts; do \
	  if [ -d "$$tmp/$$keep" ]; then cp -a "$$tmp/$$keep" "$(GATEWAY_STATIC)/"; fi; \
	done; \
	rm -rf "$$tmp"

gateway-dev: ## Run the FastAPI gateway in dev mode with real whisper dictation (:$(GATEWAY_PORT))
	LD_LIBRARY_PATH="$(NUMPY_NIX_LIBS)$$LD_LIBRARY_PATH" MAYA_ASR_BACKEND=$(MAYA_ASR_BACKEND) \
	DATABASE_URL=$(DATABASE_URL) \
	WORKSPACE_ROOT=$(WORKSPACE_ROOT) PYTHONPATH=$(WORKSPACE_ROOT):$(WORKSPACE_ROOT)/src ENV=development PORT=$(GATEWAY_PORT) uv run maya-gateway

gateway-test: ## Run the gateway pytest suite
	uv run --project apps/maya-gateway --with pytest --with pytest-anyio pytest apps/maya-gateway/tests/ -v

test: ## Run all Python unit test suites
	uv run --project apps/maya-gateway --with pytest --with pytest-anyio pytest apps/maya-gateway/tests/ -v
	uv run --project packages/maya-research --with pytest --with pytest-asyncio pytest packages/maya-research/tests/ -v
	uv run --project packages/maya-image --with pytest pytest packages/maya-image/tests/ -v
	uv run --project packages/maya-llm --extra dev --with pytest --with pytest-asyncio pytest packages/maya-llm/tests/ -v
	uv run --project packages/maya-voice --extra dev --with pytest --with pytest-asyncio pytest packages/maya-voice/tests/ -v
	uv run --project packages/maya-audio --extra dev --with pytest --with pytest-asyncio pytest packages/maya-audio/tests/ -v
	uv run --project packages/maya-voice-stack --extra dev --with pytest pytest packages/maya-voice-stack/tests/ -v -m "not gpu"
	uv run --project packages/maya-contracts --with pytest pytest packages/maya-contracts/tests/ -v
	uv run --project apps/maya-ingest --with pytest pytest apps/maya-ingest/tests/ -v

typecheck: ## Run pyright on core packages (ratchet up over time)
	uv run --with pyright pyright packages/maya-contracts/src packages/maya-llm/src packages/maya-voice/src packages/maya-audio/src packages/maya-voice-stack/src

voice-eval: ## Run fake-provider voice latency benchmarks
	uv run --project packages/maya-voice maya-voice-eval

voice-stack-test: ## Deterministic voice stack harness tests (fake providers, no GPU)
	VA_FAKE_STACK=1 uv run --project packages/maya-voice-stack --extra dev --with pytest \
	  pytest packages/maya-voice-stack/tests/ -v -m "not gpu"

voice-e2e-gpu: ## Full-stack WAV replay tests (CUDA + OpenRouter required)
	uv run --project packages/maya-voice-stack --extra dev --extra gpu --with pytest \
	  pytest packages/maya-voice-stack/tests/ -v -m gpu

voice-benchmark: ## Aggregate benchmark metrics to artifacts/voice-stack/
	VA_FAKE_STACK=1 uv run --project packages/maya-voice-stack python scripts/run_benchmark.py \
	  --fake --scenarios packages/maya-voice-stack/fixtures/scenarios.yaml --runs 3 --warmup 1

voice-e2e: e2e-deps ## Playwright voice stack web transfer test (fake stack)
	@BROWSERS=$$(nix-shell -p playwright-driver.browsers --run 'echo $$buildInputs' 2>/dev/null | awk '{print $$1}'); \
	cd $(E2E_DIR) && nix-shell -p $(NIX_PLAYWRIGHT_PKGS) --run \
	  "PLAYWRIGHT_BROWSERS_PATH=$$BROWSERS PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 VA_FAKE_STACK=1 bun x playwright test -c playwright.voice.config.ts"

e2e-deps: ## Install bun deps in tests/e2e
	cd $(E2E_DIR) && bun install

e2e-install: e2e-deps ## Install bun deps; chromium comes from nixpkgs at runtime
	@echo "Chromium is provided by nixpkgs (playwright-driver.browsers)."
	@echo "Set PLAYWRIGHT_BROWSERS_PATH=$(PLAYWRIGHT_BROWSERS_PATH) when running outside nix-shell."

e2e-test: ## Run the Playwright e2e suite (uses nixpkgs chromium on NixOS)
	@BROWSERS=$$(nix-shell -p playwright-driver.browsers --run 'echo $$buildInputs' | awk '{print $$1}'); \
	cd $(E2E_DIR) && nix-shell -p $(NIX_PLAYWRIGHT_PKGS) --run \
	  "PLAYWRIGHT_BROWSERS_PATH=$$BROWSERS PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 MAYA_FAKE_COMFY=1 bun x playwright test"

forge-uat-smoke: ## DB-free Forge UAT — gateway imagine unit tests (fake Comfy)
	MAYA_FAKE_COMFY=1 uv run --project apps/maya-gateway --with pytest --with pytest-anyio \
	  pytest apps/maya-gateway/tests/test_imagine_routes.py -v

forge-uat-e2e: ## Browser-level Forge UAT (fake Comfy, Playwright)
	@BROWSERS=$$(nix-shell -p playwright-driver.browsers --run 'echo $$buildInputs' | awk '{print $$1}'); \
	cd $(E2E_DIR) && nix-shell -p $(NIX_PLAYWRIGHT_PKGS) --run \
	  "PLAYWRIGHT_BROWSERS_PATH=$$BROWSERS PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 MAYA_FAKE_COMFY=1 bun x playwright test tests/gateway-imagine.spec.ts tests/forge-imagine-uat.spec.ts"

forge-uat-integrated: ## Integrated arena UAT — Postgres migrations + fake Comfy smoke
	$(MAKE) db-create feeds-migrate
	MAYA_FAKE_COMFY=1 DATABASE_URL=postgresql+asyncpg://$(PGUSER):$(PGUSER)@$(PGHOST):$(PGPORT)/$(PGDATABASE) \
	  $(MAKE) forge-uat-smoke

docker-build: ## Build the gateway image (multi-stage: bun homepage + uv Python)
	docker build -t maya-gateway -f apps/maya-gateway/Dockerfile .

clean-homepage: ## Remove the built SPA from the gateway static dir
	rm -rf $(GATEWAY_STATIC)/*

feeds-migrate: ## Run Alembic migrations for the maya-db package
	cd packages/maya-db && DATABASE_URL=$(DATABASE_URL) uv run alembic -c alembic.ini upgrade head

ingest-dev: ## Start a Prefect worker that runs the ingest flows
	DATABASE_URL=$(DATABASE_URL) uv run --project apps/maya-ingest prefect worker start -p default

ingest-poll: ## One-shot: run the subscription poll flow now
	DATABASE_URL=$(DATABASE_URL) uv run --project apps/maya-ingest maya-ingest poll

bootstrap-ukf: ## Bootstrap UKF label + artist follows (requires gateway on :$(GATEWAY_PORT))
	uv run --with httpx python scripts/bootstrap_ukf_follow.py

bootstrap-misskatie: ## Bootstrap MissKatie follow + homepage upload alerts
	uv run --with httpx python scripts/bootstrap_misskatie_follow.py

ingest-embed: ## One-shot: run the embedding batch flow now
	uv run --project apps/maya-ingest maya-ingest embed

ingest-backfill: ## Back-catalogue index one channel (usage: make ingest-backfill CHANNEL=<uuid>)
	@test -n "$(CHANNEL)" || (echo "usage: make ingest-backfill CHANNEL=<uuid>"; exit 2)
	uv run --project apps/maya-ingest maya-ingest backfill $(CHANNEL)

ingest-analyze: ## Analyze one GitHub release entry (usage: make ingest-analyze VIDEO=<uuid>)
	@test -n "$(VIDEO)" || (echo "usage: make ingest-analyze VIDEO=<uuid>"; exit 2)
	uv run --project apps/maya-ingest maya-ingest analyze-release $(VIDEO)

ingest-parse-intel: ## Parse YouTube description intel (usage: make ingest-parse-intel VIDEO=<uuid>)
	@test -n "$(VIDEO)" || (echo "usage: make ingest-parse-intel VIDEO=<uuid>"; exit 2)
	uv run --project apps/maya-ingest maya-ingest parse-intel $(VIDEO)

        research-test: ## Run maya-research + gateway research unit tests
	uv run --project packages/maya-research --with pytest --with pytest-asyncio pytest packages/maya-research/tests/ -v
	uv run --project apps/maya-gateway --with pytest pytest apps/maya-gateway/tests/test_research_routes.py -v

research-flow: ## Run research Prefect flow for a run id (usage: make research-flow RUN=<uuid>)
	@test -n "$(RUN)" || (echo "usage: make research-flow RUN=<uuid>"; exit 2)
	uv run --project apps/maya-ingest maya-ingest research $(RUN)

db-create: ## Create the maya_public database + required extensions (idempotent)
	@psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -tAc \
	  "SELECT 1 FROM pg_database WHERE datname='$(PGDATABASE)'" | grep -q 1 \
	  || psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) \
	     -c "CREATE DATABASE $(PGDATABASE) OWNER $(PGUSER);"
	@psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -d $(PGDATABASE) \
	  -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; CREATE EXTENSION IF NOT EXISTS vector;'

db-shell: ## Open psql against $(PGDATABASE)
	@psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -d $(PGDATABASE)

slskd-ingest-fixtures: ## Ingest breakcore + Dom & Roland + Porter/Nina fixtures into ontology
	cd $(WORKSPACE_ROOT) && uv run scripts/ingest_slskd_batch.py --all-fixtures --reconcile-porter-nina

slskd-worker: ## Run one slskd acquisition batch (ontology open_request tracks)
	cd $(WORKSPACE_ROOT) && uv run --script scripts/slskd_acquisition_worker.py -- --once

slskd-worker-loop: ## Daemon: poll ontology and enqueue slskd downloads
	cd $(WORKSPACE_ROOT) && uv run --script scripts/slskd_acquisition_worker.py -- --loop

slskd-status: ## List slskd transfer status via music query CLI
	uv run scripts/music_query_cli.py status

slskd-probe: ## Search one track via slskd (usage: make slskd-probe ARTIST=TOKYOPILL TITLE=Ethereal)
	@test -n "$(ARTIST)" || (echo "usage: make slskd-probe ARTIST=... TITLE=..."; exit 2)
	uv run scripts/music_query_cli.py search --artist "$(ARTIST)" --title "$(TITLE)" --jsonl

slskd-export-queue: ## Export ontology open_request tracks to Vault markdown queue
	cd $(WORKSPACE_ROOT) && .venv/bin/python scripts/export_slskd_queue.py

slskd-batch: ## Run Vault markdown queue batch against slskd
	cd $(WORKSPACE_ROOT) && .venv/bin/python scripts/process_music_request_batch.py --batch-size 3

slskd-history-ingest: ## Mine 90d Firefox history into ontology and export queue
	cd $(WORKSPACE_ROOT) && .venv/bin/python scripts/music_history_ingest.py --days-back 90 --export-queue

slskd-worker-once: ## Run one ontology acquisition worker batch
	cd $(WORKSPACE_ROOT) && .venv/bin/python scripts/slskd_acquisition_worker.py --once --skip-acapella --max-runtime 120

slskd-album-grab: ## Grab full album from slskd (usage: make slskd-album-grab RELEASE=dom-roland-looking-glass)
	@test -n "$(RELEASE)" || (echo "usage: make slskd-album-grab RELEASE=slug"; exit 2)
	cd $(WORKSPACE_ROOT) && .venv/bin/python scripts/slskd_album_grab.py --release "$(RELEASE)"
