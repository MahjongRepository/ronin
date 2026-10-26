# Lobby app (TypeScript / lit-html)

The scripts and styles of the server-rendered lobby pages. There is no routing: the Jinja2
templates in `backend/lobby/views/templates/` are the pages, and `src/index.ts` loads on all of them
and starts whatever the page holds (the room, the matchmaking queue, the history copy-link buttons).
`lobby-socket.ts` is the JSON lobby WebSocket; it neither reconnects nor watches for a silent server.

## Build

Vite builds one entry, `src/index.ts`, with a manifest; the lobby backend serves `dist/` under
`/lobby-assets/` and maps the entry's script and stylesheet into its templates from the manifest, or
from this app's Vite dev server under `make run-local-server` (`backend/lobby/AGENTS.md`).

## Handoff

When a game starts, the room and matchmaking pages store the game socket URL and ticket for the game
client (`session/`) and navigate to `game_client_url`/`<game_id>`. The storage key and shape are
the handoff contract in `docs/architecture.md`; change them only together with the game client.

A join refused as `already_in_game` can instead be answered with `game_starting` for the game the
user already plays, as the join's first and only message, so each page handles `game_starting`
the same way whether or not it was ever seated or queued.

## Conventions

* Imports use the `@/` alias for `src/`.
* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Page modules split like `room/`: `state.ts` (state and pure queries), `handlers.ts` (everything
  that reads or writes the socket, taking the state first), `ui.ts` (templates only, never the
  socket), `index.ts` (wiring). The server is authoritative: derive ready state, owner and start
  permission from its messages, don't keep a local copy.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for
  project-specific components. Use the `--ronin-*` tokens from `styles/_theme.scss` rather than
  literal colors and fonts. `styles/lobby-app.scss` is the one entry stylesheet.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call
the module directly. New tests go in a `__tests__/` directory beside the code. The `describe` block
names the subject (the module or function under test) and the `it` title says what it pins; tests
carry no doc comments, and source files carry no file-header comment.
