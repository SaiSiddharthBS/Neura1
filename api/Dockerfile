FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/ ./
COPY fixture/ /app/fixture/
RUN uv sync --frozen --no-dev
ENV NEURA1_FIXTURE_DIR=/app/fixture/voltline NEURA1_DATA_DIR=/app/data PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync python -m neura1.cli seed && uv run --no-sync uvicorn neura1.main:app --host 0.0.0.0 --port ${PORT}"]
