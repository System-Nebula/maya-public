FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY apps/ ./apps/

RUN uv sync --no-dev --no-cache

FROM python:3.13-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/apps /app/apps

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/packages/maya-contracts/src:/app/packages/arena-core/src:/app/packages/maya-db/src:/app/packages/obs-client/src:/app/packages/fal-client/src:/app/apps/maya-gateway/src"

EXPOSE 8080
CMD ["maya-gateway"]
