# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.11.7

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:${PYTHON_VERSION}-slim AS builder

ARG APP_PACKAGE
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /workspace

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY packages/restaurant-agent-runtime/pyproject.toml packages/restaurant-agent-runtime/pyproject.toml
COPY apps/sfcs/pyproject.toml apps/sfcs/pyproject.toml
COPY apps/bnat/pyproject.toml apps/bnat/pyproject.toml
COPY apps/elas/pyproject.toml apps/elas/pyproject.toml

RUN test -n "$APP_PACKAGE" \
    && uv sync --frozen --no-dev --package "$APP_PACKAGE" --no-install-workspace

COPY packages/restaurant-agent-runtime packages/restaurant-agent-runtime
COPY apps apps

RUN uv sync --frozen --no-dev --package "$APP_PACKAGE" --no-editable

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY gunicorn_conf.py start.sh /app/

RUN chmod +x /app/start.sh \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app /opt/venv

USER app
EXPOSE 8080
ENTRYPOINT ["/app/start.sh"]
