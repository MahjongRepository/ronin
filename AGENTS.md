# Ronin

Language rules (code, Python, JavaScript/TypeScript) come from the shared user rules. This file and
the nested `AGENTS.md` files add only what is specific to ronin, and win where they conflict. Each
nested `AGENTS.md` holds its area's architecture and rules; before planning work in an area, read it
and the `docs/` files it names for the task.

## Repository layout

Ronin is a Riichi Mahjong game server and browser client.

* `backend/` — Python 3.14 / Starlette, its own uv project (`backend/pyproject.toml`). See
  `backend/AGENTS.md`.
  * `backend/game/` — game server (WebSocket, MessagePack). See `backend/game/AGENTS.md`.
  * `backend/lobby/` — lobby server (auth, rooms, matchmaking, server-rendered pages). See
    `backend/lobby/AGENTS.md`.
  * `backend/shared/` — auth, SQLite data access, logging and helpers used by both servers.
* `frontend/` — TypeScript / lit-html / Vite / Bun: the lobby scripts and the game client SPA. See
  `frontend/AGENTS.md`.
* `deploy/` — spot playbook, production compose and the Docker image. See `deploy/AGENTS.md`.
* `bin/` — the scripts behind `make run-all-checks`, `make run-local-server`, `make deadcode` and
  `make profile`.
* `docs/` — reference read on demand: `game-protocol.md`, `lobby-api.md`, `configuration.md`,
  `game-rules.md`.
* `thoughts/` — plans and other planning artifacts; gitignored, never shipped.

## Commands

* `make run-local-server` — game server (`:8711`), lobby (`:8710`) and Vite (`:5173`) together,
  with `.env.local` sourced when present.
* `make test` / `make lint` / `make typecheck` — backend pytest, ruff, ty.
* `make test-frontend` / `make lint-frontend` / `make typecheck-frontend` — the frontend equivalents.
* `make format` / `make format-frontend` — format in place.
* `make deadcode` — unused backend code.
* `make profile` — profile the game engine replay runner (the `optimize-engine` skill uses it).
* `make run-all-checks` — every gate in order, stopping at the first failure. It **rewrites files**
  (it runs `make format`, then the backend gates, then `make format-frontend`) and **always exits 0** (`|| true`), so
  success is only the final `All checks are good` line; a failure prints `❌ CHECK FAILED` with the
  failing gate's output.

## Workflow

* While iterating, run only the tests your change touches (`cd backend && uv run pytest <path> -k <expr>`,
  `cd frontend && bunx vitest run <path>`).
* When wrapping up, run `make run-all-checks`, read its output for the success line, and report
  which checks ran.
* After a structural change, update the `AGENTS.md` of the area it touched; after a protocol,
  route, setting or rule change, update the matching `docs/` file. Keep `AGENTS.md` to architecture
  and rules: lookup tables, message shapes and file listings belong in `docs/` or nowhere.
* Commit subjects use `feat:` / `bug:` / `chore:` prefixes (the `release` skill groups by them); a
  performance change also carries a trailing `!perf` (`optimize-engine` searches for it).

## Project rules

* Tests are required for new logic; a bug fix gets a regression test.
* A test earns its place by pinning a behaviour that could plausibly break: a subtle domain rule
  (goshashonyu rounding of an exact 500 remainder, double vs single yakuman by wait pattern), a
  layered decision (pon over chi, then seat distance), or a counting edge (kyuushu kyuuhai counts
  unique terminal/honor types, not tiles). Don't write tests that restate the framework or the
  implementation: constructor fields read back, exception subclass `isinstance` checks, a dump of
  model defaults, arithmetic like `4 - num_ai_players`, or a constant's value.
* Test behaviour and outcomes, not internal mechanics, and don't duplicate a scenario another test
  already covers. Avoid `pragma: no cover` unless there is no way to reach the line.
* `except ValueError, KeyError:` (no parentheses) is valid Python 3.14 syntax (PEP 758), not a
  Python 2 leftover; don't "fix" it.
