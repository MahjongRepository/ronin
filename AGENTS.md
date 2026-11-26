# Ronin

Language rules (code, Python, Go, JavaScript/TypeScript) come from the shared user rules. This file and
the nested `AGENTS.md` files add only what is specific to ronin, and win where they conflict. Each
nested `AGENTS.md` holds the architecture and rules of its directory, down to subsystems; before
planning work, read every `AGENTS.md` on the path to the code it touches
(`git ls-files '*AGENTS.md'`).

## Repository layout

Ronin is a Riichi Mahjong game server and browser client.

* `backend/` — the two servers, each its own project with its own toolchain. See `backend/AGENTS.md`.
  * `backend/lobby/` — the lobby server (Python 3.14 / Starlette: auth, rooms, matchmaking,
    tournaments, the API the lobby pages draw from) and its admin scripts, a uv project. See `backend/lobby/AGENTS.md`.
  * `backend/game_v2/` — the game server (WebSocket, MessagePack; Go): its own Go module. See
    `backend/game_v2/AGENTS.md`.
* `frontend/` — Vite / npm on Node: two apps, each its own package built separately, sharing source from
  `frontend/shared/`. See `frontend/AGENTS.md`.
  * `frontend/lobby/` — the lobby's single-page app (TypeScript / lit-html). See
    `frontend/lobby/AGENTS.md`.
  * `frontend/game_v2/` — the game client (TypeScript / lit-html). See `frontend/game_v2/AGENTS.md`.
  * `frontend/shared/` — TypeScript source both apps import (`@ronin/shared/*`), checked by the lobby's
    toolchain. See `frontend/shared/AGENTS.md`.
* `deploy/` — spot playbook, production compose and the Docker image. See `deploy/AGENTS.md`.
* `bin/` — the scripts behind the `make` targets.
* `docs/architecture.md` — the map of how the lobby, matchmaking and the game server fit together.
* `docs/tournament-api.md` — the tournament API for external managers: starting games, the snapshot and the
  events socket.
* `docs/replay-format.md` — the stored replay file format; read before changing how replays are encoded or served.
* `docs/game-rules.md` — the Riichi ruleset the engine implements, read before rule work.
* `docs/rng.md` — how the seed becomes the walls, the first dealer and the seating, and what
  `make measure-wall` reports for it; update it with any change to the Go engine's
  `engine/internal/rng`.
* `docs/i18n.md` — the language contract and the ja/en/ru glossary; `make lint` runs
  `bin/check_i18n.py` over the lobby's catalogs.
* `docs/game-client-look.md` — the v2 game client's look (composition, elements, proportions, review
  checklist); read before any v2 board work, and change it where it contradicts common sense or the mobile
  references.
* `thoughts/` — plans and other planning artifacts; gitignored, never shipped.
* `var/` — the local runtime data of both servers (the dev database, replays, logs, profiles); gitignored,
  created by the scripts that write it.

## Commands

The `Makefile` lists the targets; the non-obvious ones:

* `make run-local-server [DOCKER=1]` — the Go game server (`:8712`, built from `backend/game_v2`), lobby
  (`:8710`) and a Vite dev server per frontend app (`:5173` lobby, `:5175` game client) together, with
  `.env.local` sourced when present. `DOCKER=1` runs the game server as its container
  (`make run-game-v2-docker`), with the lobby reading that container's replays, and stops it on exit.
  To see the app in a browser, drive it with the `agent-browser` skill plus this project's
  `app-browser` skill (`.claude/skills/app-browser/`).
* `make test` — the lobby's pytest with line coverage, which gates nothing (`backend/lobby/AGENTS.md`, Tooling).
* `make profile [BENCH=engine|router|socket]` — benchmark and profile the Go game server's full game and print
  `benchstat` and the `pprof` report (`bin/profile-full-game.sh`; the `optimize-engine` skill drives it).
  `make profile-compare BASE=<checkout> [BENCH=…]` is the `benchstat` A/B against a baseline checkout; both build with the shipped
  `cmd/gameserver/default.pgo`, which `make update-pgo [PGO_PROFILES=<cpu.prof>…]` regenerates.
* `make run-games [GAMES=n] [TABLES=t] [MODE=m] [NET=bad] [DOCKER=1]` — play bot games (the Rust `mahjong-bot` repo at `BOT_ROOT`,
  default `~/work/mahjong-bot`, built with its `make release-bot`) on fresh servers, `t` tables at a time, the bots in
  play mode `m` (their `--mode`; `chaos` misbehaves on purpose). `NET=bad`, meant for `MODE=chaos`, puts a faulty
  proxy chain between the bots and the servers; `DOCKER=1` runs the game server as a fresh container. It stops at the
  first batch with a game that is not completed, whose replay does not reproduce it, or after which any log holds a
  warning or an abnormal event such as a timeout auto-action or a bot replaced by AI. It plays against the dev
  database, so its games show on the dev lobby's history and its four bot accounts per table get fresh API keys. It
  **wipes** `var/logs/{game,lobby,net}` and the bot repo's logs first and kills whatever holds `:8710` and the game
  server's port. Run it only when asked: tests and `make run-all-checks` are the verification.
* `make profile-games` — the `make run-games` run, with its side effects, at production's INFO logging with the
  game server's profiles: where real games spend the server's CPU. `make profile` measures changes.
* `make run-tournament` — eight bots on a new tournament's page, fresh servers and the dev database, managed by
  `bin/tournament_manager.py` through the tournament API (two shuffled tables, both followed to their end); every
  API response and event goes to `var/logs/tournament/manager.log`. It wipes only `var/logs/tournament`
  and kills whatever holds `:8710`/`:8712`. Run it only when asked.
* `make measure-wall [MEASURE_ARGS=...]` — the statistics of the engine's seeds, dealers and walls (`docs/rng.md`).
  A structural failure exits 1; a statistical warning is printed, never a gate.
* `make generate-fixtures` — regenerate the v2 game client's replay fixtures and seat transcripts from
  the Go server's `cmd/fixtures` (`backend/game_v2/AGENTS.md`, Seat transcripts and Replay fixtures). `make fixtures-check` (a `run-all-checks` gate) fails when a committed file
  no longer matches what the Go server records or sends a seat.
* `make run-all-checks` — every gate in order, stopping at the first failure. It **rewrites files**
  (it runs every formatter) and **always exits 0**, so success is only the final
  `All checks are good` line; a failure prints `❌ CHECK FAILED` with the failing gate's output.

## Workflow

* While iterating, run only the tests your change touches (`cd backend/lobby && uv run pytest <path> -k <expr>`,
  `cd frontend/<app> && npx vitest run <path>`,
  `cd backend/game_v2 && mise exec -- go test ./<pkg> -run <name>`). Never run `make test` or
  `make run-all-checks` mid-work;
  `make lint` and `make typecheck` (backend only, so they run without `make install-frontend`),
  `make lint-frontend` and `make typecheck-frontend`, and `make lint-go` are fine. A Go engine change
  runs `cd backend/game_v2 && mise exec -- go test -race ./engine/... ./seam/...`: the engine's facade
  tests live in `seam/`.
* To check a visual change, screenshot only the changed area plus its single worst case (the
  smallest phone, the densest state); there is no full screenshot sweep (`frontend/game_v2/AGENTS.md`,
  Visual check).
* When a step needs no input from the user, keep going; stop and ask only when you cannot continue without
  them, or before a step these rules reserve for them (a `make -C deploy` target beyond the read-only ones,
  `make run-games`, `make run-tournament`) or anything destructive outside the disposable local stack.
* When wrapping up, run `make run-all-checks`, read its output for the success line, and report
  which checks ran.
* The local stack is disposable: restart `make run-local-server` and free its ports without asking.
  Every `make -C deploy` target acts on the production server (`TARGET` defaults to `prod`, which is
  that server): run one only when the user asks, except the read-only `spot-status`,
  `spot-check-logs-errors`, `spot-metrics`, `spot-metrics-sql` and `spot-backup-list`.
  `spot-deploy` refuses to run while the game server holds a started or pending game
  (`deploy/AGENTS.md`), so it interrupts no game running when it starts; only one created during the deploy can
  fall to the recreate, so report a game as interrupted only with evidence from that deploy.
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
* Python test names follow `test_<subject>__when_<condition>__should_<expected>`: `<condition>` is
  the scenario or input state, `<expected>` the observable outcome. Drop the `when_` clause only for
  unconditional behaviour (`test_static_css_route__should_serve_stylesheet`). `backend/lobby/AGENTS.md`
  (Tests) defines `<subject>`; Go and frontend test names follow their own `AGENTS.md`.
* Keep committed suites lean: essential flows and fixed bugs, not every nuance. To probe a nuance,
  write a throwaway test or script in the scratchpad and delete it once answered; never commit it.
* One scenario per test: several assertions about one call or one short flow are fine. Before adding
  a test, extend the scenario's existing test with an assertion.
* Never wait out a real timer or delay in a test; shorten it via settings or `monkeypatch`, and
  cover the deadline itself once.
* `except ValueError, KeyError:` (no parentheses) is valid Python 3.14 syntax (PEP 758), not a
  Python 2 leftover; don't "fix" it.
