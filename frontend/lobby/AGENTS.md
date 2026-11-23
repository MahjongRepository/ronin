# Lobby app (TypeScript / lit-html)

The lobby's pages as one single-page app. `src/index.ts` loads on every lobby page. On the shell
the server answers for every lobby route (`<main id="lobby-spa">`) it starts the app
(`app/start.ts`): the shared router (`@ronin/shared/router`) over the route list in `app/routes.ts`,
which is also the allowlist of links it intercepts and URLs it navigates to in place; any other
destination is a document navigation. On the pages that stay server-rendered (terms, privacy,
error pages) it mounts only the chrome around their `<main>`.

* **Chrome** (`app/chrome.ts`): the one nav and footer of every page, lit-html, drawn from the
  page's meta tags (CSRF token, version, release link, year, dev mode) and `GET /api/lobby/session`;
  its signed-in part waits for the session. Logout stays a form POST `/logout` that copies the
  current meta CSRF token on submit. The Admin section shows only when the session says `is_admin`.
* **Views** split like `room/` (Conventions) and export `mount<Page>View(host, ...)` returning
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
* **Data** comes from `api.ts` only, never a raw `fetch`, and is validated before use. A JSON 401
  sends the user to `/login?next=<path+query>`; a POST carries the meta CSRF token as
  `X-CSRF-Token` and retries once with the token a 403 `csrf_invalid` hands back.
* **Settings** (`settings/`) writes the same localStorage keys the game client reads, through the
  shared settings modules and rows. The server lets only signed-in users (guests included) load
  `/settings`; an in-app navigation there renders the page at once and, once the awaited session
  says nobody is signed in, replaces it with `/login?next=/settings`.
  An account also gets an API token tab beside the game settings (`settings/api-token.ts`, `/api/lobby/api-token`); a guest sees no tabs. The token
  is shown once, from the POST's answer, and never fetched again.
* **Retained pages** (`retained/`): an error page carries its status, error code and action link
  in meta tags, and `error-view.ts` words them from this app's catalog through a closed code→key map.
  The lobby storybook is a dev-only lazy route (`import.meta.env.DEV`), so production ships none of it.

The language switch never reloads or navigates. The chrome's buttons call the shared
`switchLocale` (the `lang` cookie, `<html lang>`, the wind script), re-render the chrome, then
redraw the page: an SPA view through the router's `rerender()`, an error page through its view, and
terms or privacy through `legal-swap.ts`, which refetches the page and swaps its `<main>` content and
title in place (a failed fetch keeps the old ones). The locale itself still comes from the server's
`<html lang>` at load. Text a view keeps in its state is therefore stored as a code or key and
translated at render time, except chat lines, which keep the language they arrived in.

`lobby-socket.ts` is the JSON lobby WebSocket. Its close code is the server's cue: `disconnect()`
closes with 1000, a leave, and a socket `connect()` replaces closes with 4100, so the server holds
the room seat for the new one (`backend/lobby/app/rooms/AGENTS.md`).

The room page reconnects a seated player (backoff in `room/handlers.ts`) and shows the lost
connection once it gives up. A reconnect takes the held seat
back silently; a refused one ends the page like any refused join. Returning to the page after it was
hidden for a while, or the browser coming back online, reconnects at once, since a socket can die
without a close event while the page is in the background. Matchmaking does not reconnect.

The lobby view (`lobby/`) watches the games being played over `/ws/games` (`lobby/games-feed.ts`): each message
is the whole list, which replaces the shown one, so a reconnect needs no catch-up. It reconnects with the room's
backoff and resume and binds its socket the same way. `current-games.ts` reads and draws a games list, here and on
the tournament page; the tournament socket carries no game type, so its games show only how long they have run (the view redraws it on a timer).

The tournaments page (`tournaments/`, `/tournaments`) lists the user's own tournaments, then everyone else's, and
creates new ones; it
opens for anyone signed in and every signed-in nav links to it, but a guest gets no create form (the list's
`can_create`). On phones the nav's Tournaments and Admin links move into the account menu, so the bar never
outgrows the narrowest screen.

The tournament page (`tournament/`) keeps the room's reconnect and binds its socket the same way.
It holds no seat, so a reload only reconnects, and a language switch only redraws. Its Settings tab (rename,
delete) shows when `/api/lobby/tournaments/{id}` says `is_owner`; switching tabs keeps the socket, so the owner
stays online, and a delete goes to the tournaments page. The page leads with the games: the current
ones and the game history from `joined` (every ended game, latest first), which a `game_ended` then
updates, so a reload or reconnect loses none; only the owner sees the Start game button. Who is online
and the chat sit folded below them. A finished tournament (the config's `finished_at`) opens no socket: the page
shows its name, when it finished and the game history from the config, and the owner's Settings keep rename and
delete. A live page told `tournament_finished` stops reconnecting and reloads its config into that view. The chat shows people's messages only: the chat lines of the
server's `history`, sent before `joined` on every join, replace its log, so a reconnect loses only the
page's own local error lines. `chat.ts` holds the chat log and composer both pages render.

A page that holds a lobby socket binds it to `page-lifetime.ts`: it closes the socket and cancels
any pending rejoin on `beforeunload` and again on `pagehide`, and rejoins from scratch on a `pageshow` that restores it from
the back-forward cache, unless the page has already ended (refused, taken over). Chromium keeps a
cached page's socket open and answers the server's pings for it, so without this a user who
navigates away keeps their queue entry or seat. Firefox aborts a page's sockets as soon as a
navigation starts, before `pagehide`, so without `beforeunload` the page would flash its lost
connection state while it unloads. A page leaves for the game with `location.replace`, and the room's Leave table
goes to the lobby with an in-place navigation that replaces the history entry, so Back never
restores a page whose rejoin would only hand the user the same game or seat again. For the same
reason the room and matchmaking views never reload for a language change.

## Build

Vite builds one entry, `src/index.ts`, with a manifest; the lobby backend serves `dist/` under
`/lobby-assets/` and maps the entry's script and stylesheet into its templates from the manifest, or
from this app's Vite dev server under `make run-local-server` (`backend/lobby/AGENTS.md`).
The stylesheet emits only the forced dark scheme. Storybook and developer-footer styles load
through a development-only import; the production build check rejects them and unused theme schemes.
Pico's form styles are trimmed to the lobby's inputs and chat composer. Extend this local subset
when adding a control; do not reintroduce entire upstream form or layout modules for one element.
Typography uses system sans-serif and monospace fonts, with Japanese fallback stacks selected by
the nearest `lang` attribute. The lobby makes no external font requests.

## Handoff

When a game starts, the room and matchmaking pages store the game socket URL and ticket for the game
client and navigate to `game_client_url`/`<game_id>`, both through `session/`; a `game_starting`
without a `game_id` ends the page with a way to rejoin instead. The storage key and shape are the
handoff contract in `docs/architecture.md`; change them only together with the game client.

A join refused as `already_in_game` can instead be answered with `game_starting` for the game the
user already plays, as the join's first and only message, so each page handles `game_starting`
the same way whether or not it was ever seated or queued.

A room join refused because a game is being created (`room_transitioning`, `match_starting`)
reopens the socket after a short delay, a bounded number of times, so the page follows the game once
it exists; a seated player refused the same way mid-start just waits for `game_starting`.

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
