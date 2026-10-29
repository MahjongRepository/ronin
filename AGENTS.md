# Ronin

Language rules (code, Python, JavaScript/TypeScript) come from the shared user rules. This file and
the nested `AGENTS.md` files add only what is specific to ronin, and win where they conflict. Each
nested `AGENTS.md` holds the architecture and rules of its directory, down to subsystems; before
planning work, read every `AGENTS.md` on the path to the code it touches
(`find . -name AGENTS.md -not -path '*/node_modules/*'`).

## Repository layout

Ronin is a Riichi Mahjong game server and browser client.

* `backend/` — Python 3.14 / Starlette, its own uv project. See `backend/AGENTS.md`.
  * `backend/game/` — game server (WebSocket, MessagePack). See `backend/game/AGENTS.md`.
  * `backend/lobby/` — lobby server (auth, rooms, matchmaking, server-rendered pages). See
    `backend/lobby/AGENTS.md`.
  * `backend/shared/` — auth, SQLite data access, logging and helpers used by both servers.
* `frontend/` — Vite / npm on Node: two isolated apps, each its own package. See `frontend/AGENTS.md`.
  * `frontend/lobby/` — the scripts and styles of the lobby pages (TypeScript / lit-html). See
    `frontend/lobby/AGENTS.md`.
  * `frontend/game/` — the game client (MajiangNG: JavaScript / jQuery). See `frontend/game/AGENTS.md`.
* `deploy/` — spot playbook, production compose and the Docker image. See `deploy/AGENTS.md`.
* `bin/` — the scripts behind the `make` targets.
* `docs/architecture.md` — the map of how the lobby, matchmaking and the game server fit together.
* `docs/game-rules.md` — the Riichi ruleset the engine implements, read before rule work.
* `docs/rng.md` — how the seed becomes the walls, the first dealer and the seating, and what
  `make measure-wall` reports for it; update it with any change to `game/logic/rng.py`.
* `docs/i18n.md` — the language contract and the ja/en/ru glossary; `make lint` runs
  `bin/check_i18n.py` over every app's catalogs.
* `thoughts/` — plans and other planning artifacts; gitignored, never shipped.

## Commands

The `Makefile` lists the targets; the non-obvious ones:

* `make install-frontend` — `npm ci` in each frontend app.
* `make run-local-server` — game server (`:8711`), lobby (`:8710`) and a Vite dev server per
  frontend app (`:5173` lobby, `:5174` game client) together,
  with `.env.local` sourced when present. To see the app in a browser, drive it with the
  `agent-browser` skill plus this project's `app-browser` skill (`.claude/skills/app-browser/`).
* `make test` — backend pytest with its coverage gate (`backend/AGENTS.md`, Tooling).
* `make profile` — profile the game engine replay runner (the `optimize-engine` skill uses it).
* `make run-games [GAMES=n] [TABLES=t]` — play bot games (the `mahjong-bot` repo at `BOT_ROOT`,
  default `~/work/mahjong-bot`) on fresh servers, `t` tables at a time, stopping at the first batch
  with a game that is not completed, whose replay does not reproduce it (`bin/verify_games.py`), or
  after which any log (server stderr and bot console included) holds a warning or an abnormal event
  such as a timeout auto-action or a bot replaced by AI. It forces debug console logging, so these
  gates cannot be configured away. It plays against the dev database (`AUTH_DATABASE_PATH`), so its
  games show on the dev lobby's history: it uses four bot accounts per table, because an account
  plays one game at a time, reusing each by name and issuing it a fresh API key (registering only a
  missing one), and verifies only the game ids its bots logged, so earlier games and replays are
  kept and never checked. It **wipes** `backend/logs` and the bot's `project/logs` first and kills
  whatever holds `:8710`/`:8711`.
* `make profile-games` — the same run, fixed at 48 games on 12 tables, with logging at production's
  INFO level and the game server sampling its own Python stacks per 10 ms of CPU time
  (`bin/profile_game_server.py`), then those samples by layer and function, plus its CPU-seconds per
  game. The sampler runs in-process because py-spy, pausing the server per sample, stalled it past
  the health check in most runs. It points at where real games spend the server's CPU;
  `make profile` measures engine changes.
* `make measure-wall [MEASURE_ARGS=...]` — sample games from the engine's seed, dealer and wall functions and
  report their statistics against exact references and a stdlib-shuffle control (`backend/scripts/measure_wall/`).
  A structural failure exits 1; a statistical warning is printed, never a gate. `--json` saves a run and
  `--baseline` compares with one, the loop for changing a constant in `game/logic/rng.py` and remeasuring.
* `make generate-replay-fixtures` — regenerate the game client's replay test fixtures by playing
  the scenarios of `backend/scripts/replay_fixtures/` through the engine; `make replay-fixtures-check`
  (a `run-all-checks` gate) fails when a committed fixture no longer matches what the engine records.
* `make run-all-checks` — every gate in order, stopping at the first failure. It **rewrites files**
  (it runs both formatters) and **always exits 0**, so success is only the final
  `All checks are good` line; a failure prints `❌ CHECK FAILED` with the failing gate's output.

## Workflow

* While iterating, run only the tests your change touches (`cd backend && uv run pytest <path> -k <expr>`,
  `cd frontend/<app> && npx vitest run <path>`). Never run `make test` or `make run-all-checks` mid-work;
  `make lint` and `make typecheck` are fine.
* When wrapping up, run `make run-all-checks`, read its output for the success line, and report
  which checks ran.
* After a structural change, update the nearest `AGENTS.md` it invalidates; after a rule change,
  update `docs/game-rules.md`. Keep `AGENTS.md` to architecture, invariants and rules the code
  cannot show: no route or message tables, enum value lists, env var lists or exhaustive file
  inventories — the code is their reference.
* Commit subjects use `feat:` / `bug:` / `chore:` prefixes (`bin/release-notes.sh` groups by them); a
  performance change also carries a trailing `!perf` (`optimize-engine` searches for it).

## Project rules

* Tests are required for new logic; a bug fix gets a regression test.
* A test earns its place by pinning a behaviour that could plausibly break: a subtle domain rule
  (goshashonyu rounding of an exact 500 remainder), a layered decision (pon over chi, then seat
  distance) or a counting edge (kyuushu kyuuhai counts unique terminal/honor types, not tiles).
  Don't write tests that restate the framework or the implementation: constructor fields read
  back, `isinstance` checks, a dump of model defaults, or a constant's value.
* Test behaviour and outcomes, not internal mechanics, and don't duplicate a scenario another test
  already covers.
* Backend test names follow `test_<subject>__when_<condition>__should_<expected>`: `<condition>` is
  the scenario or input state, `<expected>` the observable outcome. Drop the `when_` clause only for
  unconditional behaviour (`test_wall__should_hold_136_tiles`). `backend/AGENTS.md` defines
  `<subject>`; frontend test titles follow each app's `AGENTS.md`.
* Keep committed suites lean: essential flows and fixed bugs, not every nuance. To probe a nuance,
  write a throwaway test or script in the scratchpad and delete it once answered; never commit it.
* One scenario per test: several assertions about one call or one short flow are fine. Before adding
  a test, extend the scenario's existing test with an assertion.
* Never wait out a real timer or delay in a test; shorten it via settings or `monkeypatch`, and
  cover the deadline itself once. Exclude code from coverage only with a tag `backend/AGENTS.md`
  allows; otherwise reach the line with a test or restructure it away.
* `except ValueError, KeyError:` (no parentheses) is valid Python 3.14 syntax (PEP 758), not a
  Python 2 leftover; don't "fix" it.
