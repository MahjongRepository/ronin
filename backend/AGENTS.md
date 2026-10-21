# Backend (Python / Starlette)

Before working in `game/` or `lobby/`, read that directory's `AGENTS.md`. `shared/` holds what
both servers use: accounts, auth sessions and game tickets (`shared/auth/`), repository interfaces
(`shared/dal/`) and their SQLite implementations (`shared/db/`), replay storage
(`shared/storage.py`), logging, and the IMME meld encoding (`shared/lib/melds/`, see its
`README.md`).

## Tooling

* The uv project lives in `backend/` (`pyproject.toml`, `uv.lock`, `.venv`). It installs `game`,
  `lobby` and `shared` as packages, so imports are rooted at `backend/`
  (`from game.logic.state import ...`). `conftest.py` loads the repo-root `.env.tests` and routes
  structlog through stdlib logging so `caplog` sees it.
* Run checks from `backend/` (`cd backend && uv run pytest ...`); the ruff, ty, pytest and coverage
  paths in `pyproject.toml` are relative to it.
* Run the servers and `bin/` scripts from the repo root with `uv run --project backend ...`: their
  default paths (`frontend/dist`, `backend/storage.db`, `backend/data/replays`) are relative to it.
* `make lint` (ruff format check + ruff), `make typecheck` (ty), `make test`.

## Configuration

* Settings are pydantic-settings classes, the only list of variables: `AuthSettings`
  (`shared/auth/settings.py`, `AUTH_`), `LobbyServerSettings` (`LOBBY_`), `GameServerSettings`
  (`GAME_`); `LOG_LEVEL` / `LOG_FORMAT` are read in `shared/logging.py`.
* Both servers share `AUTH_GAME_TICKET_SECRET` (the lobby signs tickets, the game server verifies
  them) and the SQLite database at `AUTH_DATABASE_PATH`.
* `AUTH_COOKIE_SECURE` defaults to `true`; `.env.local` and `.env.tests` set it to `false`.
* Production values live in `deploy/docker-compose.yml` and the server's `/opt/ronin/.env`.

## Conventions

* Game state and domain events are frozen Pydantic models (`game/logic/state.py`); the other
  existing Pydantic families (`ServiceEvent`, the incoming messages in `game/messaging/types.py`) are
  extended in kind, keeping each family's mutability. Elsewhere — lobby room and matchmaking state,
  event routing targets — follow the shared rule: a `@dataclass` unless the data needs validation.
* Docstrings are imperative ("Calculate...", not "Calculates..."): a one-line summary, then a blank
  line and parameter/return detail only when the function is not obvious.

## Tests

* Build test data with the helpers in `game/tests/helpers/` and the suite's `conftest.py` fixtures,
  not raw tile ids or magic strings.
