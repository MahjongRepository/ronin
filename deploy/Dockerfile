ARG PYTHON_VERSION=3.14.3
ARG PYTHON_MINOR=3.14
ARG ALPINE_VERSION=3.23
ARG NODE_VERSION=26.13.0

# =============================================================================
# Stage 1: Build frontend assets
# =============================================================================
FROM node:${NODE_VERSION}-alpine AS lobby-builder

WORKDIR /app/frontend/lobby

COPY frontend/lobby/package.json frontend/lobby/package-lock.json frontend/lobby/.npmrc ./
RUN npm ci

COPY frontend/lobby/ ./

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown
ENV APP_VERSION=${APP_VERSION} GIT_COMMIT=${GIT_COMMIT} NODE_ENV=production

RUN npm run build

FROM node:${NODE_VERSION}-alpine AS game-builder

WORKDIR /app/frontend/game

COPY frontend/game/package.json frontend/game/package-lock.json frontend/game/.npmrc ./
RUN npm ci

COPY frontend/game/ ./

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown
ENV APP_VERSION=${APP_VERSION} GIT_COMMIT=${GIT_COMMIT} NODE_ENV=production

RUN npm run build

# =============================================================================
# Stage 2: Install Python dependencies
# =============================================================================
# uv images only tag by Python minor version (no patch).
FROM ghcr.io/astral-sh/uv:python${PYTHON_MINOR}-alpine${ALPINE_VERSION} AS builder

WORKDIR /app

# Enable bytecode compilation and copy mode for reproducible builds
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies first (layer cache — only re-runs when deps change)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Trim the venv: strip native extensions (~11MB), remove package metadata (~1.2MB),
# and drop the pydantic v1 compat layer (~1.2MB, incompatible with Python 3.14).
RUN apk add --no-cache binutils \
    && find /app/.venv -name '*.so' -exec strip -s {} \; \
    && apk del binutils \
    && find /app/.venv -type d -name '*.dist-info' -exec rm -rf {} + 2>/dev/null || true \
    && find /app/.venv -path '*/pydantic/v1' -type d -exec rm -rf {} + 2>/dev/null || true

# =============================================================================
# Stage 3: Trim unused modules from the Python base image
# =============================================================================
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS python-slim
ARG PYTHON_MINOR

# Remove stdlib modules unused in a headless web server container.
# The trimmed /usr/local is COPY'd into the runtime stage so deleted files
# never appear in any layer of the final image.
RUN rm -rf /usr/local/lib/python${PYTHON_MINOR}/site-packages/pip* \
           /usr/local/lib/python${PYTHON_MINOR}/ensurepip \
           /usr/local/lib/python${PYTHON_MINOR}/idlelib \
           /usr/local/lib/python${PYTHON_MINOR}/tkinter \
           /usr/local/lib/python${PYTHON_MINOR}/config-*

# =============================================================================
# Stage 4: Minimal runtime image
# =============================================================================
FROM alpine:${ALPINE_VERSION} AS runtime

# Install only the system libraries that CPython's stdlib .so modules link
# against. These are the packages present in python:3.14-alpine but absent in
# bare alpine. The Alpine version is pinned via ARG to match the Python base image.
RUN apk add --no-cache \
    ca-certificates gdbm libbz2 libffi libncursesw libpanelw libuuid \
    ncurses-terminfo-base readline sqlite-libs tzdata xz-libs zstd-libs

# Copy the trimmed Python installation (binaries, shared libs, stdlib, etc.)
# from the python-slim stage. Because rm -rf already ran there, pip/ensurepip/
# idlelib/tkinter/config-* are excluded from the copy.
COPY --from=python-slim /usr/local/ /usr/local/

WORKDIR /app

# Create non-root user
RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

# Copy Python virtual environment (dependencies only)
COPY --from=builder /app/.venv /app/.venv

# Copy backend source code.
# PYTHONPATH=/app/backend makes "import lobby", "import game", "import shared"
# work without installing the project via hatch. This matches the hatch package
# mapping: backend/lobby -> lobby, backend/game -> game, backend/shared -> shared.
COPY backend/ backend/

COPY --from=lobby-builder /app/frontend/lobby/dist /app/frontend/lobby/dist
COPY --from=game-builder /app/frontend/game/dist /app/frontend/game/dist
COPY frontend/lobby/public /app/frontend/lobby/public

# Create directories for runtime data
RUN mkdir -p /app/data/logs /app/data/replays /app/data/db && \
    chown -R app:app /app/data

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT}

USER app

EXPOSE 8710 8711
