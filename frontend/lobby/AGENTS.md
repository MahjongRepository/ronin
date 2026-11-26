# Lobby app (TypeScript / lit-html)

The lobby's pages as one single-page app, started by `src/index.ts` on the server's shell and reduced
to the chrome on the server-rendered pages (terms, privacy, error pages). `app/routes.ts` is the route
list and the allowlist of links and URLs navigated in place; any other destination is a document
navigation.

* **Chrome** (`app/chrome.ts`): the one nav and footer of every page, drawn from the page's meta tags
  (`app/page-meta.ts`) and the session; its signed-in part waits for the session, and logout is the form
  POST `/logout` carrying the current meta CSRF token.
* **Views** export `mount<Page>View(host, ...)` returning
  `{unmount, rerender}`: `unmount` closes sockets, listeners and timers and drops any fetch that
  settles after it (no socket, render or redirect after dispose); `rerender` redraws from state for
  a language switch. Each view sets `document.title` in its render.
* A view never calls `router.navigate` synchronously inside its mount or unmount, and renders its
  static frame at once while its data loads, so a route change never flashes an empty page. A list
  still loading shows `list-loading.ts`'s placeholder, sized like its loaded rows or cards, so the
  page does not jump when the data lands. The placeholder fades in only after a short delay, and loaded
  rows and cards draw without an entrance animation, so a fast answer never flashes the page. The
  tournament page fades in the same way until its socket joins, so a fast load shows only the final
  page (name, owner tabs, folds) and never the fallback name or a lone *Connecting…*.
* **Data** comes from `api.ts` only, never a raw `fetch`, and is validated before use.
* **Settings** (`settings/`) writes the same localStorage keys the game client reads, only through the
  shared settings modules and rows. The API token (`settings/api-token.ts`) is shown once, from the
  POST's answer, and never fetched again.
* **Retained pages** (`retained/`): `error-view.ts` words an error page from its meta tags. The lobby
  storybook is a development-only route; production ships none of it.

The language switch never reloads or navigates: it redraws the chrome and the page in place (an SPA
view through its `rerender`, terms and privacy through `retained/legal-swap.ts`). Text a view keeps in
its state is therefore stored as a code or key and translated at render time, except chat lines,
which keep the language they arrived in.

`lobby-socket.ts`'s close codes (leave, replace) are a contract with the server, which holds the room
seat for a replacing socket (`backend/lobby/app/rooms/AGENTS.md`); change them only together.

The room, the lobby's games feed and the tournament page reconnect with backoff, and also at once
(`bindToResume` in `page-lifetime.ts`) when the page returns from a long hide or the browser comes back
online, since a socket can die without a close event while the page is in the background.
Matchmaking does not reconnect.

`current-games.ts` reads and draws the games lists of the lobby view (`lobby/games-feed.ts`) and the tournament page.

On phones the nav's Tournaments and Admin links sit in the account menu, so the bar never outgrows the narrowest screen.

The tournament page (`tournament/`) holds no seat. Switching its tabs keeps the socket, so the owner
stays online. Every join hands it the whole game history (`joined`) and chat (`history`), so a reload or
reconnect loses nothing; a finished tournament (`finished_at`) opens no socket. `chat.ts` holds the chat
log and composer the room and tournament pages render.

A page that holds a lobby socket binds it to `page-lifetime.ts`, which releases it on both
`beforeunload` and `pagehide` and rejoins after a back-forward-cache restore. Chromium keeps a
cached page's socket open and answers the server's pings for it, so without this a user who
navigates away keeps their queue entry or seat. Firefox aborts a page's sockets as soon as a
navigation starts, before `pagehide`, so without `beforeunload` the page would flash its lost
connection state while it unloads. A page leaves for the game with `location.replace`, and the room's Leave table
goes to the lobby with an in-place navigation that replaces the history entry, so Back never
restores a page whose rejoin would only hand the user the same game or seat again. For the same
reason the room and matchmaking views never reload for a language change.

## Build

The lobby backend maps `src/index.ts`'s script and stylesheet from the Vite manifest into its templates
(`backend/lobby/AGENTS.md`), so the build keeps that one entry.
Development-only styles go through `styles/development.scss`; `scripts/check-build.ts` (run by `lint`) rejects them and any light-theme CSS in the production build.
Pico's form styles are trimmed to the lobby's inputs and chat composer. Extend this local subset
when adding a control; do not reintroduce entire upstream form or layout modules for one element.
Use the system font stacks in `styles/_theme.scss`; the lobby makes no external font requests.

## Handoff

When a game starts, the room, matchmaking and tournament pages hand off only through `session/`
(`enterGame`), which stores the game socket URL and ticket and navigates to `game_client_url`/`<game_id>`; a `game_starting`
without a `game_id` ends the page with a way to rejoin instead. The storage key and shape are the
handoff contract in `docs/architecture.md`; change them only together with the game client.

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
* Styles: the locally maintained Pico subset (`src/assets/vendor/pico/`, assembled by `styles/_pico.scss`)
  styles semantic HTML; add classes only for
  project-specific components. Use the `--ronin-*` tokens from `styles/_theme.scss` rather than
  literal colors and fonts. `styles/lobby-app.scss` is the one entry stylesheet. Block text
  inherits `color`, so set it on the wrapper; focus comes from the one shared outline in
  `_theme.scss`, so components add no focus rings of their own.
* No literal UI text in code: every string goes through `t()` from `src/i18n/` (keys typed from
  `locales/en.json`), a sentence with a link through `tParts()` and a link slot, numbers, dates and
  lists through its formatters. The locale is the page's `<html lang>`, which the server resolved;
  the scripts never resolve it, and only the in-place language switch changes it. A server code maps to a key through a closed list, and an unknown
  code shows the family's generic key and is reported (`docs/i18n.md`).
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call
the module directly. New tests go in a `__tests__/` directory beside the code. The `describe` block
names the subject (the module or function under test) and the `it` title says what it pins; tests
carry no doc comments, and source files carry no file-header comment.
