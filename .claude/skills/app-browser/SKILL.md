---
name: app-browser
description: This project's agent-browser recipes — run the local stack, log in to the ronin lobby, reach every page (room, live game, matchmaking, history, replay, storybooks) in the game client, shoot settled and targeted screenshots, and check a layout in WebKit as an iPhone. Load together with agent-browser whenever driving ronin in a browser.
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
   all servers land there.
3. Always open pages on the lobby, `http://localhost:8710`. It serves every page: lobby pages pull
   their scripts from the lobby's Vite on `:5173`, and the game client under `/play/` is proxied
   from the game's Vite on `:5175`. No Vite serves a
   page you should open.

## Logging in

Every page but `/login`, `/register`, replays and storybooks redirects anonymous users to `/login`.
There is no seed; the local user `dev` / `dev-password` lives in `backend/storage.db` once
registered:

```bash
agent-browser set viewport 1280 800
agent-browser open http://localhost:8710/login
agent-browser fill "#username" dev
agent-browser fill "#password" dev-password
agent-browser click 'form[action="/login"] button[type=submit]'
agent-browser wait 1000 && agent-browser get url
```

- Set the viewport first: a new session opens at 1280×577, where the Login button sits on the fold
  and the click silently misses it.
- To play as a guest instead, open `/login` in a logged-out session and
  `agent-browser click 'form[action="/guest"] button'`. A logged-in browser keeps its current
  identity, so each extra guest (a new `Nanashi-NNNN`) needs its own `--session`.
- Still on `/login` means the user does not exist yet: register it at `/register` the same way
  (`#username`, `#password`, `#confirm_password`), which also logs in.
- Cookies on `localhost` are shared across ports, so logging in to a second stack (the base
  worktree in `frontend/AGENTS.md` *UI changes*) logs the first one out. Drive the second stack in
  its own browser with `agent-browser --session base …` on every command, and log in there too.

## Reaching the pages

Take ids from the UI, never invent them. Templates in `backend/lobby/views/templates/` are the
lobby pages; the game client routes are in `frontend/game_v2/src/index.ts` (*The game client* below). There are no test ids: select by
element id, class or `snapshot -i` refs.

- **Room:** click `.lobby-create-btn` (Custom table) on `/`. A new room seats `dev` as host with three
  tsumogiri bots.
- **Live game:** "Start game" in the room lands on `/play/<game_id>`. `dev` then counts as playing
  until that game ends, so `/matchmaking` answers "already playing" and room joins are refused;
  that is the occupancy rule, not a bug.
- **Matchmaking:** `/matchmaking` queues for a 4-human match; one browser user only shows the
  waiting state.
- **History:** `/history` lists recent games; each card's `.games-card-link` ("View replay") opens
  `/play/history/<game_id>`. Replay controls are described below.
- **Lobby storybook:** `/storybook` shows lobby styles in development.

## The game client

The lobby serves `frontend/game_v2/` on every game page. The pages below need no login but the live game.

- **Storybooks:** `/play/storybook` and `/play/storybook/{board,decisions,discards,hand,melds,replay,rotate}`.
  A board page takes its story as `?state=<key>`; its switches (offers, callout, pinned badge,
  overlay) write their own parameters into the address, so a shot's URL reproduces it. The
  decisions page runs a generated seat transcript to a labelled checkpoint, `?state=<story>`; the
  look spec's anchor is `anchor_turn`, `anchor_call` and `anchor_riichi`. A story's board is the
  live game's box with its switches below, so shoot it at the viewport you are checking.
- **Live game:** start a game as in *Reaching the pages*; it lands on `/play/<game_id>`.
  A tab with no handoff recovers it (`GET /api/game-session`) and takes the seat over; the previous
  tab says it was replaced. To test reconnect by opening another tab, keep the current tab open:
  reloading it can empty the last human seat and end the game before the new page connects.
  Leave through `.game-menu__leave` and its Leave, so `dev` is free for the next game.
  `?debug` adds the message log.
- **Replay:** `/play/history/<game_id>`, optionally with `?seat=&round=&step=` (zero-based; a
  part the replay does not hold falls back). The moves are
  `.replay-controls__move--{first,prevRound,prev,next,nextRound,last}` and `.replay-controls__play`
  (autoplay), the options `.replay-controls__option--{speed,view,hands,rounds}`, the position
  `.replay-status__position`; a replay it cannot show gets `.replay-state` instead. Keys: ArrowLeft
  and ArrowRight step, ArrowUp, ArrowDown, PageUp and PageDown change round, Home and End go to the
  ends. The address is kept on the position shown with `history.replaceState` at most once per
  500 ms, a waiting write flushed as the page hides, so read it a moment after the last move. A
  replay recorded before a format change reads as Damaged: for a particular case, gzip a fixture
  from `frontend/game_v2/src/fixtures/replays/` into
  `backend/data/replays/<id[0:2]>/<id[2:4]>/<id>.txt.gz` under an id of your own and delete it afterwards. The speed and hidden hands are stored under
  `ronin.v2.replay-prefs` in `localStorage`: remove it after a session that changed them.

### Settled v2 screenshots

Ask for reduced motion, as the gate does, so a callout or a moving tile shows its resting state.
Routes load their chunks on their own, so first wait for a visible element that proves the state
(the gate's pages name theirs in `required.visible`; the anchor call's is its countdown), then for
the tile sprite (before it lands a face shows its short name, `5m`), the face and any animation:

```bash
agent-browser set media dark reduced-motion
agent-browser set viewport 1440 900
agent-browser open "http://localhost:8710/play/storybook/decisions?state=anchor_call"
agent-browser wait ".game-board .decision-controls__countdown"
agent-browser wait --fn "document.documentElement.dataset.tileSprite === 'ready' && document.fonts.status === 'loaded' && document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)"
agent-browser screenshot $T/<name>.png
```

For a phone, use the v2 visual check's runner rather than agent-browser (Chromium only) or a
hand-written WebKit script, for any state it has a page for: it builds nothing, so build first,
then it checks the page as well as shooting it, the notch phone's insets and capture model
included, with no backend:

```bash
cd frontend/game_v2 && npx vite build
node scripts/visual-check/run.ts --page decisions-anchor-call --viewport phone-se-landscape --shots ../../thoughts/screenshots/<topic>
```

Names match by substring and each flag repeats; given both, a page is shot at every viewport
named, whether its page entry names it or not. A filter that matches nothing prints every page and
viewport name. A state with no page there takes the *WebKit phone check* below, on the
`"iPhone SE (3rd gen) landscape"` device (667x375), in the same order: `page.wait_for_selector`
on the state's element with `state="visible"`, then the polled settle with the sprite and face
added (`document.documentElement.dataset.tileSprite === 'ready' && document.fonts.status ===
'loaded' && ` before the animations' test).

### Targeted v2 screenshots

Shoot the changed area plus one worst case (the smallest phone, or the densest state that holds
the changed element), before and after, and nothing else: never a sweep of every viewport or
story. The runner refuses a run that names no page or viewport.

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

SETTLED = "() => document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)"


def wait_settled(page, timeout_ms=5000):
    for _ in range(timeout_ms // 100):
        if page.evaluate(SETTLED):
            return
        page.wait_for_timeout(100)
    raise TimeoutError("lobby animations still running")


with sync_playwright() as p:
    device = dict(p.devices["iPhone 13"])
    device.pop("default_browser_type")
    browser = p.webkit.launch()
    page = browser.new_context(**device).new_page()
    page.goto("http://localhost:8710/login")
    page.fill("#username", "dev")
    page.fill("#password", "dev-password")
    page.click('form[action="/login"] button[type=submit]')
    page.wait_for_url("http://localhost:8710/")
    page.goto("http://localhost:8710/history")
    wait_settled(page)
    page.evaluate("document.activeElement?.blur()")
    page.screenshot(path=f"{sys.argv[1]}/phone-history.png")
    browser.close()
```

Settle with `page.evaluate` polling, not `page.wait_for_function(<string>)`: the lobby CSP has no
`unsafe-eval`, which a string predicate needs in WebKit. Run it outside the backend project, pinned
to the version whose browsers are installed:
`uv run --no-project --with playwright==1.63.0 python $S/phone.py $T`. Never `full_page=True`:
to show a whole page, set the viewport height to `document.documentElement.scrollHeight` and take a
normal screenshot. Delete the script once done.
