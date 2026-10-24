---
name: app-browser
description: This project's agent-browser recipes — run the local stack, log in to the ronin lobby, reach every page (room, live game, matchmaking, history, replay, storybooks), shoot settled screenshots, and check a layout in WebKit as an iPhone. Load together with agent-browser whenever driving ronin in a browser.
allowed-tools: Bash(agent-browser:*), Bash(curl:*)
---

# Driving ronin in agent-browser

Project recipes on top of the generic `agent-browser` skill; they override it where they conflict.
Save every screenshot to `thoughts/screenshots/<topic>/` (`$T` below), smoke checks included;
`frontend/AGENTS.md` *UI changes* sets the names for before/after pairs. Throwaway scripts go in
your scratchpad (`$S` below).

## Running the app

1. If `:8710` is already listening, the app is running — do not start a second one:
   `make run-local-server` kills whatever holds its ports. Otherwise start it with Bash
   `run_in_background: true` and leave it running across iterations; both backends run with
   `--reload` and Vite hot-reloads the frontend.
2. Wait for it: `curl -sf --retry 40 --retry-delay 1 --retry-connrefused http://localhost:8710/health`.
   If it never comes up, read the background shell's output instead of retrying; tracebacks from
   all three servers land there.
3. Always open pages on the lobby, `http://localhost:8710`. It serves every page: lobby pages pull
   their scripts from the lobby's Vite on `:5173`, and the game client under `/play/` is proxied
   from its Vite on `:5174`. Neither Vite serves a page you should open.

## Logging in

Every page but `/login`, `/register`, replays and storybooks redirects anonymous users to `/login`.
There is no seed; the local user `dev` / `dev-password` lives in `backend/storage.db` once
registered:

```bash
agent-browser set viewport 1280 800
agent-browser open http://localhost:8710/login
agent-browser fill "#username" dev
agent-browser fill "#password" dev-password
agent-browser click "button[type=submit]"
agent-browser wait 1000 && agent-browser get url
```

- Set the viewport first: a new session opens at 1280×577, where the Login button sits on the fold
  and the click silently misses it.
- Still on `/login` means the user does not exist yet: register it at `/register` the same way
  (`#username`, `#password`, `#confirm_password`), which also logs in.
- Cookies on `localhost` are shared across ports, so logging in to a second stack (the base
  worktree in `frontend/AGENTS.md` *UI changes*) logs the first one out. Drive the second stack in
  its own browser with `agent-browser --session base …` on every command, and log in there too.

## Reaching the pages

Take ids from the UI, never invent them. Templates in `backend/lobby/views/templates/` are the
lobby pages; the game client routes are in `frontend/game/src/js/routes.js`. There are no test ids:
select by element id, class or `snapshot -i` refs.

- **Room:** click `.lobby-create-btn` (New Table) on `/`. A new room seats `dev` as host with three
  tsumogiri bots.
- **Live game:** "Start Game" in the room lands on `/play/<game_id>`. `dev` then counts as playing
  until that game ends, so `/matchmaking` answers "already playing" and room joins are refused;
  that is the occupancy rule, not a bug.
- **Matchmaking:** `/matchmaking` queues for a 4-human match; one browser user only shows the
  waiting state.
- **History and replay:** `/history` lists recent games; click a card (`main article`, its
  `data-replay-url` holds `/play/history/<game_id>`). Step a replay with its `<` / `>` buttons.
- **Storybooks:** `/storybook` (lobby styles, dev only) and `/play/storybook` plus its
  `/board`, `/discards`, `/hand` and `/melds` pages (game components).

## Screenshots

- Desktop is `agent-browser set viewport 1280 800`. The game board fills the viewport and does not
  scroll, so shoot it at the viewport size you are checking rather than a taller one.
- Lobby cards fade in with staggered animations and the styles ignore `prefers-reduced-motion`.
  Wait for them before every shot, or cards come out half transparent:

  ```bash
  agent-browser wait --fn "document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)"
  agent-browser screenshot $T/<name>.png
  ```

- Read every shot. Check `agent-browser errors` after a page misbehaves; `console` is full of
  Vite and Lit dev-mode lines that mean nothing.

## WebKit phone check

`agent-browser` drives only Chromium, and iOS Safari is WebKit. Shoot phone states with a throwaway
Playwright script in the scratchpad (WebKit is already installed under `~/.cache/ms-playwright`):

```python
import sys
from playwright.sync_api import sync_playwright

SETTLED = "document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)"

with sync_playwright() as p:
    device = dict(p.devices["iPhone 13"])
    device.pop("default_browser_type")
    browser = p.webkit.launch()
    page = browser.new_context(**device).new_page()
    page.goto("http://localhost:8710/login")
    page.fill("#username", "dev")
    page.fill("#password", "dev-password")
    page.click("button[type=submit]")
    page.wait_for_url("http://localhost:8710/")
    page.goto("http://localhost:8710/history")
    page.wait_for_function(SETTLED)
    page.evaluate("document.activeElement?.blur()")
    page.screenshot(path=f"{sys.argv[1]}/phone-history.png")
    browser.close()
```

Run it outside the backend project, pinned to the version whose browsers are installed:
`uv run --no-project --with playwright==1.63.0 python $S/phone.py $T`. Never `full_page=True`:
to show a whole page, set the viewport height to `document.documentElement.scrollHeight` and take a
normal screenshot. Delete the script once done.
