ARG GO_VERSION
ARG ALPINE_VERSION=3.24

FROM golang:${GO_VERSION}-alpine${ALPINE_VERSION} AS builder
ARG GO_VERSION

WORKDIR /src

COPY mise.toml /tmp/mise.toml
RUN grep -qx "go = \"${GO_VERSION}\"" /tmp/mise.toml || { echo "GO_VERSION ${GO_VERSION} is not the Go pinned in mise.toml" >&2; exit 1; }

COPY backend/game_v2/go.mod backend/game_v2/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY backend/game_v2/ ./
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/gameserver ./cmd/gameserver

FROM alpine:${ALPINE_VERSION} AS runtime

RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

WORKDIR /app

COPY --from=builder /out/gameserver /app/gameserver
COPY backend/game_v2/THIRD-PARTY-NOTICES.md /app/THIRD-PARTY-NOTICES.md

RUN mkdir -p /app/data/replays /app/data/db && chown -R app:app /app/data

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

ENV APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT}

USER app

EXPOSE 8712

ENTRYPOINT ["/app/gameserver"]
CMD ["-addr", "0.0.0.0:8712"]
