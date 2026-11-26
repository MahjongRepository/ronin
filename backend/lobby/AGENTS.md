# Lobby server

Accounts, rooms, matchmaking, game history and the lobby pages (`:8710`); it also hosts
the game client and serves replay files, and hands players to a game server with signed game tickets.
The route table in `server/app.py` is the API reference; `rooms/AGENTS.md` covers room behaviour.

## Project

* The uv project is this directory: the package is `app/` (imports read `from app.settings import ...`),
  with `tests/` and the admin CLIs in `scripts/` beside it.
  Paths in this file are under `app/` unless they start with `tests/` or `scripts/`. The image ships
  only `app/` and `scripts/`.
* Run checks from here (`cd backend/lobby && uv run pytest ...`); run the servers and `bin/` scripts
  from the repo root with `uv run --project backend/lobby ...`, where their relative paths resolve.
* Each process opens the database once, as an `app.db.Database` (its docstrings hold the threading and
  drain model): the event loop never touches SQLite directly, and a lifespan closes the database last.

## Boundaries

`import-linter` (`[tool.importlinter]` in `pyproject.toml`, run by `make lint`) is the enforced
architecture; the contract names say the rule. It checks runtime imports only, so an
`if TYPE_CHECKING:` import still names a real dependency and must respect the same direction. A `|`
layer's packages never import each other: they share what both need through the layers below. A new
package joins a layer in the contract, or gets its own contract, in the same change.

## Tooling

* `make test` measures line coverage of `app/` and gates none of it. Keep `branch` and `fail_under` out of
  `[tool.coverage]`; branch coverage is advisory (`make coverage-branches`).
* Besides the built-in `TYPE_CHECKING` and stub exclusions, only a tagged `# pragma: no cover (<tag>)`
  excludes code from coverage; a bare one excludes nothing. Tags: `exhaustive` (the fallthrough of a
  `match` or `isinstance` chain over a closed set, or an import-time consistency check between
  enums), `entrypoint` (a production-only default the tests replace), `platform` (a branch for
  another OS). A race, a defensive catch-all or a long-running loop gets no exclusion: reach it or
  restructure it away.
* The Makefile's `DOCFORMATTER_PATHS` lists the project's top-level packages (add a new one there),
  and docformatter rewraps a triple-quoted call argument as a docstring: assign it to a variable first.
* `make lint` and `make format` run ruff over `bin/` too, under `bin/ruff.toml`; relax it only for what
  a CLI script needs.

## Configuration

* One pydantic-settings class per concern; the classes are the only list of variables.
* Deployment-specific values are required fields: `deploy/docker-compose.yml` supplies them in
  production, `bin/local-settings.sh` locally, and `.env.tests` in tests, where the paths point at
  `/nonexistent/` so a test that touches them must pass its own `tmp_path`.
* The metrics database path is required as well, though the file may be missing: it is the host
  collector's `metrics.db`, read-only to the lobby (mounted `:ro` in production), and a missing file shows
  as "never collected" on the monitoring page rather than failing startup.

## Conventions

* Validated data (wire messages, persistence models) is a Pydantic model; extend an existing Pydantic
  family in kind, and use a `@dataclass` elsewhere unless the data needs validation.
* Docstrings are imperative ("Calculate...", not "Calculates..."): a one-line summary, then a blank
  line and parameter/return detail only when the function is not obvious.
* No module docstrings or file-header comments: what a module must convey goes on its classes and
  functions.

## Tests

* Tests build the app through the fixtures in `tests/conftest.py`.
* Tests carry no docstrings (module, class, test or helper): the test name, and the names of its
  variables, say what it pins; a rename is the way to carry a non-obvious setup.
* `<subject>` in a test name (root naming rule) is the function, rule or component under test, in
  snake_case: `matchmaking_queue`, `login_route`, `replay_file_path`. A method in a `Test*`
  class carries the full name too; the class only groups.
* Test logic once, at the lowest layer that owns it: unit tests in `tests/unit/` load no app. Integration tests in `tests/integration/` cover only the
  wiring (routing, serialization, auth, error mapping) and never re-check manager or model logic
  through a socket or HTTP.
* One error test per mechanism, not per field or route: Pydantic's built-in constraints need none; a
  custom validator or a raised domain exception gets one.
* Prefer real I/O against ephemeral resources (`tmp_path`, a temporary SQLite database) over mocks;
  mock only at process boundaries (sockets, the network).
* Build test data with the helpers in `tests/helpers/` and each package's `conftest.py` fixtures,
  not magic strings.

## Structure

* `server/` — the composition root: `create_app()` builds the services onto `app.state`.
* `auth/` — accounts, sessions, game tickets, the authentication backend, the route policy decorators and CSRF;
  `CredentialSockets` (`auth/socket_registry.py`) cuts off the lobby sockets of a credential the service revokes.
* `dal/` — the persistence contracts and models; `db/` — their SQLite implementations.
* `views/` — page and API handlers by domain, the Jinja2 templates, and the lobby app's Vite manifest / dev-server
  resolution into template globals. Every lobby page route answers `shell.html` (`spa_handlers.py`) under its own
  policy decorator, and the lobby app (`frontend/lobby/`) draws the page from `/api/lobby/*`; only terms, privacy
  and error pages render server content, through `base.html`, which holds the chrome's mounts around `<main>` and
  no navigation of its own. The chrome's POST `/logout` is the one HTML form; a new one validates CSRF (Security
  requirements).
  `game_client.py` hosts the game client (`frontend/game_v2/`); the game page must keep the lobby's origin for the
  `sessionStorage` handoff (`docs/architecture.md`, Game client contract).
* `views/error_pages.py` — every error answer, the failed CSRF check included.
* Storybook pages and footer links are development-only.
* `i18n/` — the en/ja/ru catalogs, the locale resolver and the `Translator` (`docs/i18n.md` is the contract). The server resolves
  each page's locale into `<html lang>`; its catalog holds only the page titles the layout and the legal pages
  print. Page, nav, footer and error text is the lobby app's: the server sends codes (`AuthErrorCode`, error
  codes, room errors), never English prose; bot JSON, plain-text and protocol answers stay English. The server
  never writes the `lang` cookie: only the clients' language switches do, on an explicit choice.
* `rooms/` and `matchmaking/` — managers and WebSocket handlers.
* `game_transition.py` — the one game start for rooms, matchmaking and tournaments, the game server client calls,
  the "is this user playing" lookup and the recovery of a lost handoff. `websocket_utils.py` — the socket prologue every lobby socket shares (auth, `Origin` check, accept, the writer's lifetime);
  each handler decides what an unexpected error does.
* `monitoring/` — the admin monitoring page's data from the host collector's `metrics.db`, which `report.py` turns
  into the JSON the lobby app draws; `scripts/monitoring_report.py` prints the same report for agents. The reader
  never goes through `app.db`, which would force WAL and create a schema on the collector's file, and reductions run
  in SQL, so a long range never loads raw samples.
* `occupancy.py` — the one owner of the occupancy rule.
* Tournaments and `tournament_games` (the games started for one, players East to North) are rows in the shared
  SQLite database. `views/tournament_handlers.py` is the lobby app's tournament API; a tournament's page, the
  shareable link, opens for anyone signed in, guests included. Creation is gated by
  `TOURNAMENT_CREATION_CLOSED` there; a guest never creates one.
* `tournaments/` — the tournament page's socket, `TournamentHub` (who is online, the events subscribers and the chat
  history, in memory only) and the game-end poller. Being online on a tournament page is no occupancy place.
  `chat_messages.py` holds the chat message model and the client frame limits both rooms and tournaments use.
* The tournament API (`views/tournament_api_handlers.py`) is for an external manager; `docs/tournament-api.md` is its
  contract.
* A game's exit route (`/games/{game_id}/exit`, outside `/play/`) decides where leaving a game leads by its game id
  alone: a `tournament_games` row sends the player to that tournament's page, anything else to the lobby. Nothing
  about the return rides in the handoff, which is cleared at the game end, so a reload on the end screen still finds
  it.
* A tournament rename reaches no other open page: no event carries it.
* The schema is the files of `db/migrations/NNNN_<name>.sql`, applied in one transaction (`db/schema.py`), so a
  migration holds no transaction control. An applied migration is never edited; a fix is a new one. `0000_initial`
  keeps `IF NOT EXISTS`: the game server creates `played_games` in the same file on its own and may start first.
* `live_games/` — the lobby page's list of the games being played (`/ws/games`); like "playing" (Occupancy), it comes
  only from the game server's in-memory sessions.
* The one game server is two settings never derived from each other: the internal URL the lobby
  calls and the public WebSocket origin it hands clients.

## Occupancy

* A user is in at most one place: one room seat, the matchmaking queue (queued or matched), or one
  game they are playing. A rejected join is told the reason and closed.
* A join to the place the user already holds (their seat in the same room, full or not, or their
  unmatched queue entry) takes it over instead: the new connection keeps the seat, readiness and
  arrival (so host succession) or the queue position, and the old one is told
  `replaced_by_new_connection` and closed. This is how a reload, a second tab or the room page's
  reconnect gets past a dead socket the server has not noticed yet, or takes back a seat held for
  a lost connection (`rooms/AGENTS.md`). When two connections of
  one user join at once, the last one admitted wins, which is the one whose playing lookup finished
  last, not necessarily the newest. A place is never traded for another, except a room seat held for a
  lost connection, which a successful join elsewhere releases (`rooms/AGENTS.md`), and never taken over once
  its game is being created: a transitioning room refuses every join, and a matched user is
  refused as `match_starting` (by a room join too), retryable answers that the handoff recovery
  turns into the game once it exists.
* Everything keyed by connection (ready, start, leave, chat, cleanup) misses for a taken-over
  connection, so its buffered input and late cleanup change nothing.
* "Playing" comes only from the game server's in-memory sessions, never from `played_games`, whose
  `ended_at` stays NULL after a crash. That lookup fails open (`game_transition.is_user_playing`), with the game
  server's own refusal as the backstop.
* The WebSocket joins are the only gates: room creation does not check.

## Handoff recovery

* A join refused as `already_in_game` is answered with the user's live game as `game_starting`
  when the game server can name it, so a lost handoff is repaired by any lobby join; the game page
  recovers through `GET /api/game-session`. The room page of a room that is gone redirects a
  playing user to their game's page (to the lobby when they play none or the lookup fails). The flow is in `docs/architecture.md`.
* Recovery returns the participant's own ticket from the game server (`game_transition.find_game_handoff`); the
  lobby never caches or re-signs tickets, and its lookup never fails open.

## Auth model

* Humans register and log in with username and password and get a session cookie. Every session is
  a human's; bots have none.
* Sessions persist in the shared SQLite database as SHA-256 hashes of the cookie token; the raw token
  lives only in the cookie. Session writes are awaited, never posted, so a logout cannot be lost.
  Login (register and guest login included) replaces the incoming cookie's session, and the
  session-creating writes purge expired rows, so no cleanup task runs.
* Session lifetimes are the constants at the top of `auth/service.py`: the expiry slides on use up to an absolute
  cap, which the cookie carries as its Max-Age; only the database expiry slides. A renewal never revives a
  deleted or expired row.
* A guest is a session without an account: a fresh user id, a generated `Nanashi-NNNN` name and no
  `players` row, gone at logout or expiry. Several places still treat the name as identity (the game
  server rejects a table with duplicate names), so the name is unique among live guest sessions,
  chosen and inserted in one write transaction so two concurrent guest logins cannot share it; the
  hyphen keeps it out of the account namespace. Accepted limit: a guest who logs out, logs in to an
  account, or expires while still seated frees the name, and a new guest drawing it at that table
  breaks the game start.
* Guest login is rate-limited per client IP (a token bucket in process memory, reset by a restart),
  because each guest holds one of the 9000 names for up to 7 idle days; an exhausted pool fails
  every guest login. The IP is uvicorn's proxy-header client address, which Traefik sets.
* Bots register through `scripts/register_bot.py` under an `ai-` name, a prefix no human can register, and get an API key, printed once and never stored;
  run for an existing bot, the script rotates its key, which invalidates the old one. Bots send the
  key as `X-API-Key` on the bot API and the WebSocket handshakes, which skip the `Origin` check
  (Security requirements); from the handshake on, a bot runs the human code path.
* An account becomes an admin through `scripts/grant_admin.py` (`--revoke` takes the flag back); the
  flag lives on the player record and is the only admin concept.
* A registered human gets an API token on the settings page: one per account, shown once, stored
  only as the same SHA-256 hash in the same field as a bot's key; generating again rotates it. A guest
  has no account and so no token. The token grants everything the account can do.

## Security requirements

Mandatory for all lobby code; review must catch violations.

* Every HTML form POST validates the CSRF token (`validate_csrf`, `views/error_pages.py`); bot API routes and the
  key-only `api_key_json` routes are exempt.
* Every lobby JSON POST (`/api/lobby/*`) reads its body through `parse_json_body` and checks the `X-CSRF-Token`
  header against the cookie (`is_csrf_valid`) before any side effect. A stale token is answered 403 `csrf_invalid`
  with the cookie's token, or a new one set as the cookie under `render_page`'s cross-site rule
  (`json_csrf_rejection`); the client retries once with it. Every answer a lobby API handler
  produces is `Cache-Control: no-store`.
* Every request body is capped by `RequestBodyLimitMiddleware` (`server/middleware.py`; its docstring says why
  Starlette's own does not fit). A handler reads its body before any side effect, so a rejected body changes nothing.
  Never raise the cap for one route: it also keeps bot JSON far below the parser's recursion depth.
* Every HTTP route gets exactly one policy decorator from `auth/policy.py`; startup fails for a `Route` without one. WebSocket routes
  authenticate inside the handler. `protected_json` and `admin_json` are for JSON a page script fetches: a
  JSON 401, never a login redirect.
* `admin_html` and `admin_json` read the account's admin flag on every request, never from the session, so a
  grant or revoke applies at the next request. Any session without the flag, a guest's included, gets a 404
  (`admin_json`: JSON `not_found`). Only
  the chrome's Admin nav section links an admin route, and it shows only when `/api/lobby/session` says
  `is_admin`; the lobby bundle's monitoring chunk is discoverable, but its data is not.
* Unknown `Host` headers are rejected; a new deployment host goes in the allowed-hosts setting.
* Session and CSRF cookies are HttpOnly, SameSite=Lax and Secure by default; only the tests and local HTTP
  development (`.env.tests`, `.env.local`) turn Secure off. The `lang` cookie is the one exception to HttpOnly: it carries no
  credential and the game client reads it at page load; every reader validates it against
  the supported locales.
* A redirect to a client-supplied target (the login `next`) follows only a same-site path: no
  scheme, no host, no `//` or backslash, nothing unprintable; anything else goes to the lobby.
* Credentials never travel in a URL: uvicorn and Traefik log every path with its query string. A
  response carrying a credential (a game ticket) is `Cache-Control: no-store`.
* The internal API secret is sent only to the game server, as a bearer header; no page or browser
  response ever holds it.
* Every lobby WebSocket (`websocket_utils.py`) refuses an unauthenticated socket with 4001, then a
  cookie-authenticated one with 4003 when its `Origin` is not exactly the configured one, a setting every
  deployment must supply. A key-authenticated handshake on any lobby socket is exempt from the `Origin` check: it
  defends the cookie a browser attaches to a cross-site socket, and no browser sends an `X-API-Key` on its own.
* A new route fits one of the two CSP tiers (`server/middleware.py`) or gets an explicit policy.
* Replay serving reads files only through `replay_storage.read_replay`, which keeps the id checks,
  path traversal protection and size limit.
* Passwords, API keys, session ids and game tickets are never logged at INFO or above.
