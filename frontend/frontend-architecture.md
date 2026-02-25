# Frontend Architecture

Two distinct frontend applications — a server-rendered lobby and a standalone game client SPA — sharing a common design system and build toolchain.

**Stack**: TypeScript, lit-html, Pico CSS v2, Sass, Bun

## Applications

### Lobby App

Server-rendered HTML pages via Jinja2 templates (served by the lobby backend at port 8710). The lobby app has no client-side routing — each page is a full HTML document rendered by the backend.

**Pages**:
- `/login` — Login form (public)
- `/register` — Registration form (public)
- `/` — Room listing with create/join actions (authenticated)
- `/rooms/{room_id}` — Room page with WebSocket-powered player list and chat (authenticated)
- `/styleguide` — Lobby component showcase (public, dev only)

The room page (`/rooms/{room_id}`) is the only lobby page with client-side JavaScript. It loads `lobby/index.ts` which reads `data-room-id` and `data-ws-url` attributes from the DOM and initializes a WebSocket connection for real-time room interactions (player list, chat, ready state).

**Templates** (in `backend/lobby/views/templates/`):
- `base.html` — Base layout with Google Fonts, nav block, main container, sticky footer
- `lobby.html` — Room grid with diamond seat visualization and "New Table" card
- `room.html` — Minimal shell; room UI rendered client-side via lit-html
- `login.html`, `register.html` — Auth forms with centered card layout

### Game Client App

Standalone SPA served at `/game` via a Jinja2 template that injects content-hashed asset URLs. Uses hash-based routing (`#/game/{gameId}`) and communicates with the game server via MessagePack over WebSocket.

**Entry point**: `index.html` → `src/index.ts` → hash router → game view

**Connection flow**:
1. Lobby room page stores game session data (WebSocket URL, game ticket) in `sessionStorage` when all players ready up
2. Browser navigates to `/game#/game/{gameId}`
3. Game client reads session from `sessionStorage`, connects to game server WebSocket
4. Client sends `JOIN_GAME` with HMAC-signed game ticket
5. On disconnect, client auto-reconnects with `RECONNECT` using the same ticket

**State machine** (`GameConnectionState`):
- `joining` → initial connection, sends `JOIN_GAME`
- `playing` → game active, reconnects send `RECONNECT` instead of `JOIN_GAME`

## Design System

### Typography
- **Display**: Syne (geometric, 400–800 weights) — headings, branding
- **Body**: DM Sans (9–40 optical size, 400–600 weights) — all body text
- **Mono**: JetBrains Mono (400–500 weights) — room IDs, timestamps, code

### Color Palette (Dark Theme)
- **Background layers**: `#0c1018` → `#141c28` → `#1a2334`
- **Primary accent**: `#4ecca3` (jade/teal)
- **Text**: `#dce0e8` (primary), `#8b91a0` (secondary), `#5c6779` (muted)
- **Semantic**: `#4ecca3` (success), `#e05252` (danger), `#e8a849` (warning), `#d4a855` (gold)

### CSS Framework
Pico CSS v2.1.1 configured via `_pico.scss` with jade theme color and selective module loading. Pico provides base styling for semantic HTML elements (`<article>`, `<nav>`, `<button>`, `role="group"`, etc.) — custom classes are used only for project-specific components.

### CSS Architecture

```
src/styles/
├── lobby-app.scss     # Lobby entry point (imports all lobby styles)
├── game-app.scss      # Game entry point (imports all game styles)
├── _pico.scss         # Pico CSS v2 configuration (theme, modules)
├── _theme.scss        # Design tokens, global font application, sticky footer layout
├── _lobby.scss        # Lobby page styles (nav, room cards, seats, auth, footer, animations)
├── _room.scss         # Room page styles (player list, chat, connection status)
└── _game.scss         # Game client styles (log panel, status badges)
```

Both apps share `_pico.scss` and `_theme.scss` for consistent theming. Custom properties are defined in two layers:
- Pico overrides (`[data-theme="dark"]`) — standard Pico variables like `--pico-background-color`, `--pico-primary`
- Project tokens (`:root`) — `--ronin-surface`, `--ronin-border`, `--ronin-font-display`, etc.

## Lobby Components

### Room Card (`lobby-room-card`)
Card displaying room info with a diamond seat visualization. Shows room ID (monospace), player count, and seat occupancy via 4 dots arranged in N-E-S-W pattern around a center square (mimicking a mahjong table from above). Filled seats glow jade; empty seats are dashed outlines. Cards animate in with staggered delays. Hover reveals a jade accent line at the top edge.

### Create Table Card (`lobby-create-btn`)
Dashed-border card with a "+" icon and "New Table" label. On hover, border and text transition to jade with a subtle background tint.

### Diamond Seat Visualization (`lobby-table-vis`)
CSS Grid layout with named areas (`a`, `b`, `c`, `d` for N/E/S/W seats, `t` for center table). The center table is rendered as a `::after` pseudo-element. Each seat is a 10px circle positioned via `nth-child` grid-area assignments.

### Footer (`footer-content`)
Sticky footer (pushed to bottom via flexbox `min-height: 100vh` on body). Shows copyright year and version on the left. In dev mode (`APP_VERSION == "dev"`), shows links to lobby and game styleguides on the right. Wraps on mobile via `flex-wrap`.

## Lobby TypeScript

### Room Module (`lobby/room.ts`)
Manages room page state and rendering. Uses lit-html to render player list, chat messages, and ready button. Handles WebSocket messages for player join/leave, ready state changes, chat, and game transitions.

### Lobby Socket (`lobby/lobby-socket.ts`)
Lightweight WebSocket wrapper for the lobby room protocol (JSON text frames). Provides connect/disconnect, message sending, and status callbacks. Sends periodic ping heartbeats (10s interval).

## Game Client TypeScript

### Router (`router.ts`)
Hash-based SPA router. Matches `#/game/{gameId}` routes. Runs cleanup callbacks on route changes. Falls back to lobby URL redirect for unmatched routes.

### Game Socket (`websocket.ts`)
WebSocket client for the game server (MessagePack binary frames). Features:
- Auto-reconnect with exponential backoff (up to 10 attempts, max 30s delay)
- Periodic ping heartbeats (10s interval)
- Connection state tracking (connecting, connected, disconnected, error)

### Protocol (`protocol.ts`)
Enum definitions matching the game server's wire protocol:
- `ClientMessageType` — integer-keyed client→server messages (JOIN_GAME=7, RECONNECT=6, GAME_ACTION=3, CHAT=4, PING=5)
- `EventType` — integer-keyed server→client game events (DRAW=1, DISCARD=2, ROUND_END=4, etc.)
- `GameAction` — integer-keyed player actions (DISCARD=0, DECLARE_RIICHI=1, CALL_RON=3, etc.)
- `SessionMessageType` — string-keyed session messages (game_reconnected, session_error, etc.)
- `ConnectionStatus` — client-side connection states

### Game View (`views/game.ts`)
Renders a development log panel showing raw game events. Handles the join → play → reconnect lifecycle. Auto-confirms round ends after 1s delay. Handles permanent and transient reconnection errors (retry with backoff for `reconnect_retry_later`, redirect to lobby for permanent errors).

### Session Storage (`session-storage.ts`)
Persists game session data (WebSocket URL, game ticket) in `sessionStorage` for reconnection across page navigations. Data is stored per `gameId` key.

### Environment (`env.ts`)
Reads runtime configuration:
- `__LOBBY_URL__` from `env.js` (injected at runtime for dev mode)
- `APP_VERSION` and `GIT_COMMIT` injected at build time via Bun's `define` option

## Build System

### Toolchain
- **Bun** — Package manager, TypeScript bundler, script runner
- **Sass** (Dart Sass 1.97) — SCSS compilation with `--load-path=node_modules` for Pico CSS imports
- **TypeScript** 5.9 — Strict mode, ES2022 target
- **oxlint** — JavaScript/TypeScript linter
- **stylelint** — SCSS linter (standard-scss config)
- **oxfmt** — Code formatter

### Build Targets

**Lobby** (`bun run build:lobby` → `scripts/build-lobby.ts`):
1. Compiles `lobby-app.scss` → compressed CSS
2. Content-hashes CSS → `dist/lobby-{hash}.css`
3. Bundles `lobby/index.ts` → minified JS → `dist/lobby-{hash}.js`
4. Updates `dist/manifest.json` with `lobby_css` and `lobby_js` entries

**Game** (`bun run build:game` → `scripts/build-game.ts`):
1. Compiles `game-app.scss` → `public/styles/game.css`
2. Bundles `index.html` entry point with minification and version defines
3. Content-hashes output → `dist/index-{hash}.js`, `dist/game-app-{hash}.css`
4. Writes `dist/manifest.json` with `js` and `css` entries

**Dev mode** (`bun run dev` → `scripts/dev.sh`):
- Bun dev server with hot reloading for the game client
- Sass watch mode for lobby CSS (`bun run sass:lobby:watch`)
- Lobby backend serves static CSS from `frontend/public/`

### Asset Serving

The lobby backend discovers built assets via `dist/manifest.json` and injects content-hashed URLs as Jinja2 template globals (`lobby_css_url`, `lobby_js_url`, `game_css_url`). In dev mode without a production build, it falls back to un-hashed paths from `frontend/public/`.

## Project Structure

```
frontend/
├── index.html              # Game client HTML entry point (dev + build input)
├── logo.svg                # Project logo
├── package.json            # Dependencies, scripts
├── tsconfig.json           # TypeScript config (strict, ES2022)
├── dist/                   # Build output (content-hashed assets + manifest)
│   └── manifest.json       # Maps logical names to hashed filenames
├── public/                 # Static files served by lobby backend in dev mode
│   ├── styles/
│   │   ├── lobby.css       # Compiled lobby styles (dev, un-hashed)
│   │   └── game.css        # Compiled game styles (dev, un-hashed)
│   └── env.js              # Runtime environment config (__LOBBY_URL__)
├── scripts/
│   ├── build-lobby.ts      # Lobby build script (Sass + Bun bundle + manifest)
│   ├── build-game.ts       # Game build script (Bun bundle + manifest)
│   └── dev.sh              # Dev server launcher
└── src/
    ├── index.ts             # Game client entry point (router setup)
    ├── router.ts            # Hash-based SPA router
    ├── env.ts               # Runtime environment helpers
    ├── protocol.ts          # Wire protocol enums (message types, events, actions)
    ├── websocket.ts         # GameSocket (MessagePack, auto-reconnect)
    ├── session-storage.ts   # Game session persistence in sessionStorage
    ├── lobby/
    │   ├── index.ts         # Room page initialization (reads DOM data attributes)
    │   ├── room.ts          # Room state and lit-html rendering
    │   └── lobby-socket.ts  # Lobby WebSocket wrapper (JSON frames)
    ├── views/
    │   └── game.ts          # Game view (log panel, join/reconnect lifecycle)
    └── styles/
        ├── lobby-app.scss   # Lobby CSS entry point
        ├── game-app.scss    # Game CSS entry point
        ├── _pico.scss       # Pico CSS v2 config (jade theme, selective modules)
        ├── _theme.scss      # Design tokens, fonts, sticky footer
        ├── _lobby.scss      # Lobby styles (nav, cards, seats, auth, footer)
        ├── _room.scss       # Room page styles (players, chat)
        └── _game.scss       # Game client styles (log panel, status badges)
```

## Dependencies

### Runtime
- `lit-html` (3.3) — Lightweight HTML template rendering (no virtual DOM)
- `@msgpack/msgpack` (3.1) — MessagePack encode/decode for game server communication
- `@picocss/pico` (2.1) — Classless CSS framework with dark theme support

### Development
- `bun-types` — Bun API type definitions
- `sass` (1.97) — Dart Sass SCSS compiler
- `typescript` (5.9) — TypeScript compiler (type checking only; Bun handles bundling)
- `oxlint` — Fast JavaScript/TypeScript linter
- `oxfmt` — Code formatter
- `stylelint` + `stylelint-config-standard-scss` — SCSS linter
