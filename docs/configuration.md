# Configuration

Environment variables read by the servers. Default paths are relative to the repo root, where the
servers run (`make run-local-server` sources `.env.local`; tests load `.env.tests`). Production
values live in `deploy/docker-compose.yml` and the server's `/opt/ronin/.env` (`deploy/README.md`).

## Shared (`AUTH_`, `LOG_`)

- `AUTH_GAME_TICKET_SECRET` — HMAC-SHA256 secret for game tickets; required, same value on both
  servers
- `AUTH_DATABASE_PATH` — SQLite database shared by both servers (default `backend/storage.db`)
- `AUTH_COOKIE_SECURE` — Secure flag on cookies (default `true`; `false` for local HTTP)
- `AUTH_PASSWORD_HASHER` — `bcrypt` (default) or `simple` (tests)
- `LOG_LEVEL` (default `INFO`), `LOG_FORMAT` (`json` in production)

## Lobby (`LOBBY_`)

- `LOBBY_CONFIG_PATH` — game server registry (default `backend/config/servers.yaml`); the lobby
  health-checks every listed server on each request that needs one, with no caching
- `LOBBY_ALLOWED_HOSTS` — accepted `Host` headers, JSON array or CSV (default `localhost`,
  `127.0.0.1`, `testserver`, `*.local`)
- `LOBBY_WS_ALLOWED_ORIGIN` — accepted WebSocket `Origin` (default `http://localhost:8710`)
- `LOBBY_CORS_ORIGINS` — JSON array or CSV (default empty)
- `LOBBY_STATIC_DIR` (default `frontend/public`), `LOBBY_GAME_ASSETS_DIR` (default `frontend/dist`)
- `LOBBY_GAME_CLIENT_URL` (default `/play`)
- `LOBBY_REPLAY_DIR` — replay root (default `backend/data/replays`)
- `LOBBY_VITE_DEV_URL` — Vite dev server for HMR (`http://localhost:5173` under
  `make run-local-server`; empty serves the built assets)
- `LOBBY_LOG_DIR` — file logging for local dev (default empty: stdout only)

## Game server (`GAME_`)

- `GAME_MAX_CAPACITY` (default 100)
- `GAME_REPLAY_DIR` (default `backend/data/replays`)
- `GAME_CORS_ORIGINS` — JSON array or CSV
- `GAME_LOG_DIR` — file logging for local dev (default empty: stdout only)
