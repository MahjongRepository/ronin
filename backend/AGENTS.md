# Backend (Python / Starlette)

Before working in `game/` or `lobby/`, read that directory's `AGENTS.md`. `shared/` holds what
both servers use: auth sessions, password hashing and game tickets (`shared/auth/`), the
persistence contracts and their models (`shared/dal/`: `Player`, `AccountType`, `PlayedGame`,
repository interfaces) and the SQLite implementations (`shared/db/`), replay storage
(`shared/storage.py`), logging, and the IMME meld encoding (`shared/lib/melds/`, see its
`README.md`).

## Boundaries

`import-linter` (`[tool.importlinter]` in `pyproject.toml`, run by `make lint` as `lint-imports`)
is the enforced architecture; the contract names say the rule. It checks runtime imports only
(`exclude_type_checking_imports`), so an `if TYPE_CHECKING:` import still names a real dependency
and must respect the same direction. The rules it pins:

* `game` and `lobby` never import each other; `shared` imports neither, nor `scripts`.
* `game`: `server` → `session` → `messaging` → `wire` → `logic`; `replay` is a tool over `logic` and
  `wire` that never imports the server packages, and `session` never imports `replay`. `logic` and
  `wire` know nothing of auth or persistence.
* `lobby`: `server` → `views` → `rooms` | `matchmaking` → `game_transition` | `websocket_utils` →
  `auth` | `registry` → `settings`; `rooms` and `matchmaking` are independent of each other. What
  both need from the other is injected in `create_app()` (matchmaking's `is_user_in_room`).
* `shared`: `db` → `auth` → `dal`; only the two `server/app.py` composition roots, `scripts` and the
  `shared` tests import `shared.db`.

A new package joins a layer in the contract, or gets its own contract, in the same change.

## Tooling

* The uv project lives in `backend/` (`pyproject.toml`, `uv.lock`, `.venv`). It installs `game`,
  `lobby` and `shared` as packages, so imports are rooted at `backend/`
  (`from game.logic.state import ...`). `conftest.py` loads the repo-root `.env.tests` and routes
  structlog through stdlib logging so `caplog` sees it.
* Run checks from `backend/` (`cd backend && uv run pytest ...`); the ruff, ty, pytest and coverage
  paths in `pyproject.toml` are relative to it.
* Run the servers and `bin/` scripts from the repo root with `uv run --project backend ...`: the
  relative asset defaults (`frontend/dist`, `frontend/public`) and the database and replay paths
  `bin/local-settings.sh` sets resolve against it.
* `make lint` (docformatter check + ruff format check + ruff), `make typecheck` (ty), `make test`.
  `make test` enforces coverage: it runs the whole suite with line-only `--cov`, then gates
  `game/logic/` and `game/wire/` at 100% line coverage with its own `coverage report`; the rest of
  the backend is measured, not gated. `addopts` leaves `--cov` out so a path-scoped
  `uv run pytest <path>` runs just that path. Branch coverage is advisory: `make coverage-branches`
  reports it for the whole backend with no threshold. Keep `branch` and `fail_under` out of
  `[tool.coverage]`: `coverage report` has no line-only mode, so branch data would turn the line gate
  into a branch gate, and a configured threshold would fail the advisory report.
* Besides the built-in `if TYPE_CHECKING:` and `...` stub exclusions, only a tagged
  `# pragma: no cover (<tag>)` excludes code from coverage; a bare `# pragma: no cover` excludes
  nothing. The tags: `exhaustive` (the fallthrough of a `match` or `isinstance` chain over a
  closed set, or an import-time consistency check between enums), `entrypoint` (a production-only
  factory or composition-root default the tests replace), `platform` (a branch for an OS the suite
  does not run on). A line justified as a race, rare, a defensive catch-all or a long-running loop
  gets no exclusion: reach it with a test, or restructure until the branch is gone or type-checked.
* docformatter formats nothing when given `.`, so the Makefile's `DOCFORMATTER_PATHS` lists the backend's
  top-level packages and modules: add a new one there. It exits 3 when it changed files, which
  `make format` treats as success. It also rewraps a triple-quoted string passed directly as a call
  argument as if it were a docstring: assign the literal to a variable first, or add the file to the
  `[tool.docformatter]` exclude list (which matches bare filenames), as `test_dead_code.py` is.

## Configuration

* Settings are pydantic-settings classes, the only list of variables and the only way application
  code reads the environment (never `os.environ`): `AuthSettings` (`shared/auth/settings.py`,
  `AUTH_`), `LobbyServerSettings` (`lobby/settings.py`, `LOBBY_`), `GameServerSettings`
  (`game/server/settings.py`, `GAME_`), `LoggingSettings` (`shared/logging.py`, no prefix).
* A safe application default (timeouts, capacity, cookie and hasher choice, asset paths inside the
  app layout) stays in the class. A deployment-specific value (secrets, the database, replay and
  server-list paths, allowed hosts and origins) is a required field with no default, so a
  misconfigured deployment fails at startup: `deploy/docker-compose.yml` supplies it in production,
  `bin/local-settings.sh` (sourced by `bin/run-local-server.sh`) locally, and `.env.tests` in tests,
  where the paths point at `/nonexistent/` so a test that touches them must pass its own `tmp_path`.
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
* No module docstrings or file-header comments: what a module must convey goes on its classes and
  functions.

## Tests

* Tests carry no docstrings (module, class, test or helper): the test name, and the
  names of its variables, say what it pins. The comment gate rejects new comments, so a rename is the
  way to carry a non-obvious setup.
* `<subject>` in a test name (root naming rule) is the function, rule or component under test, in
  snake_case: `declare_riichi`, `pao`, `furiten`, `matchmaking_queue`, `login_route`. A method in a
  `Test*` class carries the full name too; the class only groups. Example:
  `test_furiten__when_player_discarded_the_winning_tile__should_forbid_ron`.
* Test logic once, at the lowest layer that owns it: engine rules in `game/tests/unit/`. Integration
  tests cover only the wiring (routing, serialization, auth, error mapping) and never re-check engine
  or service logic through a socket or HTTP.
* One error test per mechanism, not per field or route: Pydantic's built-in constraints need none; a
  custom validator or a raised `GameRuleError` subclass gets one.
* Plain `assert`, fixtures over setup methods, `@pytest.mark.parametrize` over copy-pasted cases.
* Prefer real I/O against ephemeral resources (`tmp_path`, a temporary SQLite database) over mocks;
  mock only at process boundaries (sockets, the network).
* Build test data with the helpers in `game/tests/helpers/` and the suite's `conftest.py` fixtures,
  not raw tile ids or magic strings.
