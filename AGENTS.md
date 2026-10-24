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
* `frontend/` — TypeScript / lit-html / Vite / Bun: the lobby scripts and the game client SPA. See
  `frontend/AGENTS.md`.
* `deploy/` — spot playbook, production compose and the Docker image. See `deploy/AGENTS.md`.
* `bin/` — the scripts behind the `make` targets.
* `docs/architecture.md` — the map of how the lobby, matchmaking and the game server fit together.
* `docs/game-rules.md` — the Riichi ruleset the engine implements, read before rule work.
* `thoughts/` — plans and other planning artifacts; gitignored, never shipped.

## Commands

The `Makefile` lists the targets; the non-obvious ones:

* `make run-local-server` — game server (`:8711`), lobby (`:8710`) and Vite (`:5173`) together,
  with `.env.local` sourced when present. To see the app in a browser, drive it with the
  `agent-browser` skill plus this project's `app-browser` skill (`.claude/skills/app-browser/`).
* `make test` — backend pytest with its coverage gate (`backend/AGENTS.md`, Tooling).
* `make profile` — profile the game engine replay runner (the `optimize-engine` skill uses it).
* `make run-all-checks` — every gate in order, stopping at the first failure. It **rewrites files**
  (it runs both formatters) and **always exits 0**, so success is only the final
  `All checks are good` line; a failure prints `❌ CHECK FAILED` with the failing gate's output.

## Workflow

* While iterating, run only the tests your change touches (`cd backend && uv run pytest <path> -k <expr>`,
  `cd frontend && bunx vitest run <path>`). Never run `make test` or `make run-all-checks` mid-work;
  `make lint` and `make typecheck` are fine.
* When wrapping up, run `make run-all-checks`, read its output for the success line, and report
  which checks ran.
* After a structural change, update the nearest `AGENTS.md` it invalidates; after a rule change,
  update `docs/game-rules.md`. Keep `AGENTS.md` to architecture, invariants and rules the code
  cannot show: no route or message tables, enum value lists, env var lists or exhaustive file
  inventories — the code is their reference.
* Commit subjects use `feat:` / `bug:` / `chore:` prefixes (the `release` skill groups by them); a
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
  `<subject>`; frontend test titles follow `frontend/AGENTS.md`.
* Keep committed suites lean: essential flows and fixed bugs, not every nuance. To probe a nuance,
  write a throwaway test or script in the scratchpad and delete it once answered; never commit it.
* One scenario per test: several assertions about one call or one short flow are fine. Before adding
  a test, extend the scenario's existing test with an assertion.
* Never wait out a real timer or delay in a test; shorten it via settings or `monkeypatch`, and
  cover the deadline itself once. Exclude code from coverage only with a tag `backend/AGENTS.md`
  allows; otherwise reach the line with a test or restructure it away.
* `except ValueError, KeyError:` (no parentheses) is valid Python 3.14 syntax (PEP 758), not a
  Python 2 leftover; don't "fix" it.
