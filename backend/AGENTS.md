# Backend (Python / Starlette)

Before working in `game/` or `lobby/`, read that directory's `AGENTS.md`. `shared/` holds what
both servers use:

* `shared/auth/` — auth sessions, password hashing and game tickets.
* `shared/dal/` — the persistence contracts and models; `shared/db/` — their SQLite implementations.
* `shared/storage.py` — replay storage.
* `shared/websocket.py` — the per-connection queued writer and the pre-accept handshake helpers.
* `shared/rate_limit.py` — the token-bucket rate limiter; `shared/logging.py` — structlog setup.
* `shared/lib/melds/` — the IMME meld encoding (see its `README.md`).

Each process opens the database once, as a `shared.db.Database`: one worker thread owns the SQLite
connection and runs operations in call order, so the event loop never waits on SQLite. A write nobody
awaits (the game records) is posted and never raises — its failure is logged with the game id — and
the lifespans close the database last, within a bounded drain.

## Boundaries

`import-linter` (`[tool.importlinter]` in `pyproject.toml`, run by `make lint`) is the enforced
architecture; the contract names say the rule. It checks runtime imports only, so an
`if TYPE_CHECKING:` import still names a real dependency and must respect the same direction. A `|`
layer's packages never import each other: they share what both need through the layers below. A new
package joins a layer in the contract, or gets its own contract, in the same change.

## Tooling

* The uv project lives in `backend/` and imports are rooted there (`from game.logic.state import ...`).
  Run checks from `backend/` (`cd backend && uv run pytest ...`); run the servers and `bin/` scripts
  from the repo root with `uv run --project backend ...`, where their relative paths resolve.
* `conftest.py` loads the repo-root `.env.tests` and routes structlog through stdlib logging so
  `caplog` sees it.
* `make test` gates `game/logic/` and `game/wire/` at 100% line coverage; the rest is measured, not
  gated. Keep `branch` and `fail_under` out of `[tool.coverage]` or the gate breaks; branch coverage
  is advisory (`make coverage-branches`).
* Besides the built-in `TYPE_CHECKING` and stub exclusions, only a tagged `# pragma: no cover (<tag>)`
  excludes code from coverage; a bare one excludes nothing. Tags: `exhaustive` (the fallthrough of a
  `match` or `isinstance` chain over a closed set, or an import-time consistency check between
  enums), `entrypoint` (a production-only default the tests replace), `platform` (a branch for
  another OS). A race, a defensive catch-all or a long-running loop gets no exclusion: reach it or
  restructure it away.
* The Makefile's `DOCFORMATTER_PATHS` lists the backend's top-level packages (add a new one there),
  and docformatter rewraps a triple-quoted call argument as a docstring: assign it to a variable first.

## Configuration

* One pydantic-settings class per concern; the classes are the only list of variables.
* Deployment-specific values are required fields: `deploy/docker-compose.yml` supplies them in
  production, `bin/local-settings.sh` locally, and `.env.tests` in tests, where the paths point at
  `/nonexistent/` so a test that touches them must pass its own `tmp_path`.
* Both servers share the game ticket secret (the lobby signs tickets, the game server verifies them),
  the internal API secret (the lobby's bearer token on the game server's credential-returning
  lookup) and the SQLite database.

## Conventions

* Game state and domain events are frozen Pydantic models; extend an existing Pydantic family in kind,
  and use a `@dataclass` elsewhere unless the data needs validation.
* Docstrings are imperative ("Calculate...", not "Calculates..."): a one-line summary, then a blank
  line and parameter/return detail only when the function is not obvious.
* No module docstrings or file-header comments: what a module must convey goes on its classes and
  functions.

## Tests

* Tests carry no docstrings (module, class, test or helper): the test name, and the names of its
  variables, say what it pins; a rename is the way to carry a non-obvious setup.
* `<subject>` in a test name (root naming rule) is the function, rule or component under test, in
  snake_case: `declare_riichi`, `furiten`, `matchmaking_queue`, `login_route`. A method in a `Test*`
  class carries the full name too; the class only groups.
* Test logic once, at the lowest layer that owns it: engine rules in `game/tests/unit/`. Integration
  tests cover only the wiring (routing, serialization, auth, error mapping) and never re-check engine
  or service logic through a socket or HTTP.
* One error test per mechanism, not per field or route: Pydantic's built-in constraints need none; a
  custom validator or a raised `GameRuleError` subclass gets one.
* Prefer real I/O against ephemeral resources (`tmp_path`, a temporary SQLite database) over mocks;
  mock only at process boundaries (sockets, the network).
* Build test data with the helpers in `game/tests/helpers/` and the suite's `conftest.py` fixtures,
  not raw tile ids or magic strings.
