# Frontend Architecture

Two distinct frontend applications — a server-rendered lobby and a standalone game client SPA — sharing a common design system and build toolchain.

**Stack**: TypeScript, lit-html, Pico CSS v2, Sass, Vite, Bun

**Import alias**: All imports use `@/` mapped to `src/` (configured in `tsconfig.json` paths and `vite.config.ts` resolve alias). Use `@/shared/protocol` instead of relative protocol imports, etc.

## Applications

### Lobby App

Server-rendered HTML pages via Jinja2 templates (served by the lobby backend at port 8710). The lobby app has no client-side routing — each page is a full HTML document rendered by the backend.

**Pages**:
- `/login` — Login form (public)
- `/register` — Registration form (public)
- `/` — Room listing with create/join actions (authenticated)
- `/history` — Completed game history with replay links (authenticated)
- `/rooms/{room_id}` — Room page with WebSocket-powered player list and chat (authenticated)
- `/styleguide` — Lobby component showcase (public, dev only)

Lobby JavaScript (`lobby/index.ts`) loads on all lobby pages via `base.html`. On the room page (`/rooms/{room_id}`), it reads `data-room-id` and `data-ws-url` attributes from the DOM and initializes a WebSocket connection for real-time room interactions (player list, chat, ready state). On other pages, it acts as a no-op since no `#room-app` element exists.

**Templates** (in `backend/lobby/views/templates/`):
- `base.html` — Base layout with Google Fonts, nav block, main container, sticky footer
- `lobby.html` — Room grid with diamond seat visualization and "New Table" card
- `room.html` — Minimal shell; room UI rendered client-side via lit-html
- `login.html`, `register.html` — Auth forms with centered card layout

### Game Client App

Standalone SPA served at `/play/{gameId}` via a Jinja2 template that injects content-hashed asset URLs. Uses pathname-based routing and communicates with the game server via MessagePack over WebSocket. Also serves replay viewing at `/play/history/{gameId}` (HTTP fetch, no WebSocket).

**Entry point**: `src/index.ts` (Vite entry) → pathname router → game view or replay view

**Connection flow**:
1. Lobby room page stores game session data (WebSocket URL, game ticket) in `sessionStorage` when the room owner starts the game
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
├── lobby/             # Lobby page styles (split into component partials)
│   ├── _index.scss    # Barrel file (@forward all partials)
│   ├── _nav.scss      # Nav bar, brand, logo, nav links
│   ├── _alert.scss    # Alert banner
│   ├── _rooms.scss    # Room grid, cards, seat visualization, create form
│   ├── _auth.scss     # Auth card, auth links
│   ├── _footer.scss   # Footer content, dev links, error text
│   ├── _games.scss    # Game history cards, standings, badges
│   └── _animations.scss # card-in, slide-down keyframes
├── _melds.scss        # Meld component styles (upright, sideways, stacked tiles)
├── _hand.scss         # Hand component styles (tile row, drawn tile gap)
├── _discards.scss     # Discard component styles (rows, grayed, sideways riichi)
├── _room.scss         # Room page styles (player list, chat, connection status)
├── _game.scss         # Game client styles (log panel, status badges)
└── _storybook.scss    # Storybook layout (tile rows, cells)
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
CSS Grid layout with named areas (`a`, `b`, `c`, `d` for N/E/S/W seats, `t` for center table). The center table is rendered as a `::after` pseudo-element. Each seat is a 10px circle positioned via `nth-child` grid-area assignments. Human seats glow jade with solid borders; bot seats use dashed borders and transparent backgrounds.

### Footer (`footer-content`)
Sticky footer (pushed to bottom via flexbox `min-height: 100vh` on body). Shows copyright year and version on the left. In dev mode (`APP_VERSION == "dev"`), shows links to lobby and game styleguides on the right. Wraps on mobile via `flex-wrap`.

## Lobby TypeScript

### Room Module (`lobby/room/`)
Manages room page state and rendering, split into four files by responsibility:

- **`state.ts`** — `RoomState` interface and `createRoomState()` factory. Encapsulates player list, chat messages, connection status, ownership, and socket reference. Pure state queries (`getMyReadyState`).
- **`handlers.ts`** — All functions that read or write to the socket: inbound WebSocket message handlers (`onRoomJoined`, `onPlayerJoined`, `onPlayerLeft`, `onPlayerReadyChanged`, `onOwnerChanged`, `onGameStarting`) and outbound user action callbacks (`handleToggleReady`, `handleStartGame`, `handleSendChat`, `handleLeaveRoom`). Each function receives `RoomState` as its first argument.
- **`ui.ts`** — Pure lit-html templates and render functions. Receives state for reading and action callbacks for event bindings. Never touches `state.socket` directly.
- **`index.ts`** — Public API (`initRoomPage`). Wires state, handlers, and UI together.

Uses lit-html to render a fixed 4-seat player list (humans and bot placeholders), chat messages, and action buttons. Ready state is server-authoritative — the UI derives the current player's ready state from the server's `players` array rather than maintaining a local toggle.

The room owner (creator) sees a "Start Game" button that enables when all non-owner humans are ready (`can_start` from server). Non-owner players see a "Ready" / "Not Ready" toggle. Handles WebSocket messages: `room_joined` (with `is_owner`, `can_start`), `player_joined`, `player_left`, `player_ready_changed`, `owner_changed` (host transfer), `start_game` (client-to-server), chat, and game transitions.

### Lobby Socket (`lobby/lobby-socket.ts`)
Lightweight WebSocket wrapper for the lobby room protocol (JSON text frames). Provides connect/disconnect, message sending, and status callbacks. Sends periodic ping heartbeats (10s interval).

## Game Client TypeScript

### Router (`router.ts`)
Pathname-based SPA router. Routes:
- `/play/storybook` — Component storybook index page (no WebSocket, dev-only)
- `/play/storybook/discards` — Storybook discard pile showcase (no WebSocket, dev-only)
- `/play/storybook/hand` — Storybook hand variants showcase (no WebSocket, dev-only)
- `/play/storybook/melds` — Storybook meld types showcase (no WebSocket, dev-only)
- `/play/history/{gameId}` — Replay view (fetches and displays completed game events via HTTP)
- `/play/{gameId}` — Live game view (WebSocket connection to game server)

Runs cleanup callbacks on route changes. Falls back to lobby URL redirect for unmatched routes.

### Game Socket (`shared/websocket/websocket.ts`)
WebSocket client for the game server (MessagePack binary frames). Features:
- Auto-reconnect with exponential backoff (up to 10 attempts, max 30s delay)
- Periodic ping heartbeats (10s interval)
- Connection state tracking (connecting, connected, disconnected, error)

### Protocol (`shared/protocol/`)
Self-contained wire protocol module using Zod schemas and const objects (replacing legacy TypeScript enums). Provides:
- **Constants** (`constants.ts`) — all wire protocol values as `as const` objects with derived union types (EVENT_TYPE, CLIENT_MESSAGE_TYPE, GAME_ACTION, SESSION_MESSAGE_TYPE, PLAYER_ACTION, CALL_TYPE, ROUND_RESULT_TYPE, WIND, KAN_TYPE, MELD_TYPE, CONNECTION_STATUS, etc.)
- **Decoders** (`decoders/`) — pure functions decoding compact wire integers: `decodeDraw` (packed seat+tile), `decodeDiscard` (packed seat+tile+flags), `decodeMeldCompact` (IMME 15-bit meld encoding)
- **Schemas** (`schemas/`) — Zod schemas parsing all 19 server message types (12 game events + 7 session messages) from wire-format aliases to typed camelCase objects
- **Message parser** (`schemas/message.ts`) — `parseServerMessage()` entry point returning Result tuple `[Error, null] | [null, ParsedServerMessage]`, routes by discriminator (string `type` for session, integer `t` for game events)
- **Builders** (`builders/client-messages.ts`) — 14 type-safe factory functions for client-to-server messages
- **Types** (`types.ts`) — Zod-inferred TypeScript types for all parsed messages

### Game View (`views/game.ts`)
Renders a development log panel showing parsed game events (camelCase objects via `parseServerMessage()`). Handles the join → play → reconnect lifecycle using protocol builder functions (`buildJoinGameMessage`, `buildReconnectMessage`, `buildConfirmRoundAction`). Auto-confirms round ends after 1s delay. Handles permanent and transient reconnection errors (retry with backoff for `reconnect_retry_later`, redirect to lobby for permanent errors). Falls back to raw JSON logging when parsing fails.

### Storybook Views (`views/storybook.ts`, `views/storybook-melds.ts`, `views/storybook-hand.ts`, `views/storybook-discards.ts`)
Developer-facing component showcase with a multi-page structure. The main page at `/play/storybook` renders all 37 tile faces organized by suit, back tile display, wire ID conversion demo (`tile136toString`), and links to sub-pages. Sub-pages: `/play/storybook/discards` showcases discard pile variants (basic rows, overflow, grayed-out claimed tiles, sideways riichi tiles, mixed); `/play/storybook/hand` showcases hand variants (face up, face down, with/without drawn tile, small hand); `/play/storybook/melds` showcases all meld types (chi, pon, open/closed kan, added kan) with examples. Navigation is shared via `storybook-nav.ts` (4 pages: Index, Discards, Hand, Melds). Used for visual testing of game UI components.

### Tile Config (`entities/tile/lib/tile-config.ts`)
Single source of truth for the active tile set and dimensions. Exports `TILE_FACES_SET` (face sprite folder name, e.g. `"fluffy-stuff"`) and `TILE_WIDTH`/`TILE_HEIGHT` (60×80 px). Used by the sprite build script, tile rendering, and storybook display.

### Tile Utilities (`entities/tile/lib/tile-utils.ts`)
Pure utility module for the 136-format tile ID system. Provides `tile136toString(tileId)` to convert server wire IDs to display names (with red five aka-dora detection) and constants (`TILE_FACES`, `FIVE_RED_MAN/PIN/SOU`, `RED_FIVES`).

### Tile Component (`entities/tile/ui/tile.ts`)
Rendering layer for mahjong tiles. Every tile carries a face identity (`TileFace`) and the caller chooses the display mode. `Tile(face, show)` renders either the face sprite (`show: "face"`) or the back SVG image (`show: "back"`) — the face identity is preserved in both modes but only visible when showing the face. All tiles are wrapped in a `<span class="tile">` container. Tile dimensions are defined once in `tile-config.ts` (`TILE_WIDTH=60`, `TILE_HEIGHT=80`). Face tiles use SVG sprite `<use>` references; back tiles render the full back SVG. `injectSprite()` handles one-time injection of the tile sprite into the DOM. Both sprite and back SVG are loaded via Vite `?raw` static imports.

### Hand Component (`entities/tile/ui/hand.ts`)
Renders a horizontal row of 1–14 mahjong tiles with an optional drawn tile separated by a visible gap. `Hand(tiles, drawnTile?)` takes an array of `HandTile` objects (each with `face: TileFace` and `show: "face" | "back"`) and an optional drawn tile. Tiles render inside a `<span class="hand">` container using `inline-flex` with `1px` gap (matching the Meld layout pattern). Each tile is wrapped in `<span class="hand-tile">`. The drawn tile gets an additional `hand-drawn-gap` class with `8px` left margin to visually separate it from the main hand. Styles live in `_hand.scss`.

### Discards Component (`entities/tile/ui/discards.ts`)
Renders a player's discard pile as rows of face-up tiles. `Discards(tiles)` takes an array of `DiscardTile` objects (each with `face: TileFace` and optional `grayed`/`riichi` booleans) and returns a `TemplateResult`. Tiles are arranged in a `<span class="discards">` flex-column container with up to 3 `<span class="discard-row">` rows (inline-flex, 1px gap, `align-items: flex-end`). Row splitting: tiles 0–5 go to row 1, 6–11 to row 2, 12+ to row 3 (row 3 has no max). Empty rows are not rendered. Each tile is wrapped in `<span class="discard-tile">` with optional `.discard-tile-grayed` (opacity 0.35, indicates tile was claimed by another player) and `.discard-tile-riichi` (sideways 90deg rotation using the same absolute-position technique as meld sideways tiles, indicates riichi declaration). Styles live in `_discards.scss`.

### Replay View (`views/replay.ts`)
Displays completed game replay events fetched via HTTP from `/api/replays/{gameId}`. Uses the same log panel UI as the game view but without WebSocket connection. Fetches replay NDJSON via `fetch()` with `AbortController` for cleanup. Parses NDJSON lines (skipping the version tag), runs each through `parseServerMessage()` to produce typed camelCase objects, renders parsed event type and formatted JSON in the log panel. Falls back to raw line display on parse failure. Shows "Replay" status badge and "Back to History" navigation.

### Session Storage (`shared/session/session-storage.ts`)
Persists game session data (WebSocket URL, game ticket) in `sessionStorage` for reconnection across page navigations. Data is stored per `gameId` key.

### Environment (`shared/config/env.ts`)
Reads configuration:
- `VITE_LOBBY_URL` from `import.meta.env` (build-time via `.env.development`), falls back to `"/"` in production (same origin)

## Build System

### Toolchain
- **Vite** 6.x — Build tool with HMR dev server, content hashing, and manifest generation
- **Bun** — Package manager and script runner
- **Sass** (Dart Sass 1.97) — SCSS preprocessing (Vite peer dependency)
- **TypeScript** 5.9 — Strict mode, ES2023 target
- **SVGO** 4.x — SVG optimizer for tile sprite generation
- **oxlint** — JavaScript/TypeScript linter
- **stylelint** — SCSS linter (standard-scss config)
- **oxfmt** — Code formatter

### Build Targets

Two Vite entry points configured in `vite.config.ts`:

**Game** (`src/index.ts`):
- Imports `./styles/game-app.scss`
- Produces content-hashed JS and extracted CSS in `dist/assets/`

**Lobby** (`src/lobby/index.ts`):
- Imports `../styles/lobby-app.scss`
- Produces content-hashed JS and extracted CSS in `dist/assets/`

`bun run build` runs `vite build`, which produces `dist/.vite/manifest.json` mapping source entry points to their hashed output files. CSS is extracted into separate files (no CSS-in-JS at runtime).

**Tile Sprite** (`bun run sprite [name]`):
- Runs `scripts/build-tile-sprite.ts`
- Accepts optional CLI arg for tile set name; defaults to `TILE_FACES_SET` from `tile-config.ts`
- Reads individual SVGs from `src/assets/tiles/faces/{name}/`
- Optimizes with SVGO and combines into `src/assets/tiles/sprites/{name}.svg`
- Generated file is committed to git; run only when tile SVGs change

**Dev mode** (`bun run dev`):
- Vite dev server on port 5173 with HMR for TypeScript and SCSS
- Lobby backend connects to Vite when `LOBBY_VITE_DEV_URL` is set

### Asset Serving

Production: the lobby backend reads `dist/.vite/manifest.json` and injects content-hashed URLs as Jinja2 template globals (`lobby_css_url`, `lobby_js_url`, `game_css_url`, `game_js_url`). Built assets are served at `/game-assets/` with Vite's `base: "/game-assets/"` ensuring correct CSS `url()` resolution.

Dev mode: when `LOBBY_VITE_DEV_URL` is set, template globals point to the Vite dev server (e.g., `http://localhost:5173/src/index.ts`). CSS URLs point to SCSS source files, which Vite compiles on the fly.

## Project Structure

```
frontend/
├── vite.config.ts          # Vite build configuration (2 entry points, base path)
├── svgo.config.js          # SVGO optimization config (strip Inkscape metadata)
├── .env.development        # Dev-mode env vars (VITE_LOBBY_URL)
├── package.json            # Dependencies, scripts
├── tsconfig.json           # TypeScript config (strict, ES2023, vite/client types)
├── scripts/
│   └── build-tile-sprite.ts # Sprite generation (combines 37 SVGs into one)
├── dist/                   # Build output (content-hashed assets)
│   ├── assets/             # Hashed JS, CSS, SVG files
│   └── .vite/
│       └── manifest.json   # Vite manifest mapping source to hashed outputs
├── public/                 # Static files served by lobby backend at /static/
└── src/
    ├── index.ts             # Game client entry point (imports game-app.scss)
    ├── router.ts            # Pathname-based SPA router
    ├── zod-setup.ts         # Global Zod configuration
    ├── entities/
    │   └── tile/
    │       ├── index.ts              # Public API barrel
    │       ├── ui/
    │       │   ├── tile.ts           # Tile rendering (SVG sprite + back)
    │       │   ├── hand.ts           # Hand component (horizontal tile row)
    │       │   ├── meld.ts           # Meld component (upright, sideways, stacked)
    │       │   └── discards.ts       # Discards component (discard pile rows)
    │       └── lib/
    │           ├── tile-config.ts    # Active tile set config (face set, dimensions)
    │           └── tile-utils.ts     # Tile ID conversion (136-format to names)
    ├── shared/
    │   ├── config/
    │   │   ├── index.ts              # Public API barrel
    │   │   └── env.ts                # Environment helpers (lobby URL)
    │   ├── session/
    │   │   ├── index.ts              # Public API barrel
    │   │   └── session-storage.ts    # Game session persistence in sessionStorage
    │   ├── websocket/
    │   │   ├── index.ts              # Public API barrel
    │   │   └── websocket.ts          # GameSocket (MessagePack, auto-reconnect)
    │   └── protocol/
    │       ├── index.ts              # Public API (re-exports)
    │       ├── constants.ts          # Wire protocol const objects & union types
    │       ├── types.ts              # Zod-inferred type re-exports
    │       ├── schemas/
    │       │   ├── common.ts         # Shared schema helpers (tileId, seat, wireScore, playerInfo)
    │       │   ├── events.ts         # 10 game event Zod schemas
    │       │   ├── session.ts        # 6 session message schemas
    │       │   ├── reconnect.ts      # Reconnection snapshot schema
    │       │   ├── round-results.ts  # 6 round end result variant schemas
    │       │   ├── call-prompt.ts    # 3 call prompt variant schemas
    │       │   └── message.ts        # Top-level parseServerMessage() router
    │       ├── decoders/
    │       │   ├── draw.ts           # Packed draw integer decoder
    │       │   ├── discard.ts        # Packed discard integer decoder
    │       │   └── meld.ts           # IMME meld compact decoder
    │       └── builders/
    │           └── client-messages.ts # Client-to-server message builders
    ├── assets/
    │   ├── logo.svg         # Project logo (content-hashed by Vite)
    │   └── tiles/
    │       ├── faces/
    │       │   └── fluffy-stuff/    # Source tile SVGs (37 individual files)
    │       ├── backs/
    │       │   └── classic-yellow.svg  # Tile back SVG
    │       └── sprites/
    │           └── fluffy-stuff.svg    # Combined SVG sprite (37 symbols, generated)
    ├── lobby/
    │   ├── index.ts         # Lobby entry point (imports lobby-app.scss)
    │   ├── games-history.ts # History page interactions (card click navigation, copy replay link)
    │   ├── lobby-socket.ts  # Lobby WebSocket wrapper (JSON frames)
    │   └── room/
    │       ├── index.ts     # Public API (initRoomPage), wires state/handlers/UI
    │       ├── state.ts     # RoomState interface and factory
    │       ├── handlers.ts  # WebSocket message handlers and user action callbacks
    │       └── ui.ts        # lit-html templates and render functions
    ├── views/
    │   ├── game.ts          # Game view (log panel, join/reconnect lifecycle)
    │   ├── replay.ts        # Replay view (HTTP fetch, log panel, no WebSocket)
    │   ├── storybook.ts     # Component storybook (tile gallery, UI demos)
    │   ├── storybook-melds.ts # Storybook meld showcase page
    │   ├── storybook-hand.ts  # Storybook hand showcase page
    │   ├── storybook-discards.ts # Storybook discards showcase page
    │   └── storybook-nav.ts   # Shared storybook navigation component
    └── styles/
        ├── lobby-app.scss   # Lobby CSS entry point
        ├── game-app.scss    # Game CSS entry point
        ├── _pico.scss       # Pico CSS v2 config (jade theme, selective modules)
        ├── _theme.scss      # Design tokens, fonts, sticky footer
        ├── lobby/           # Lobby styles (split into component partials)
        │   ├── _index.scss  # Barrel (@forward all partials)
        │   ├── _nav.scss    # Nav bar, brand, logo
        │   ├── _alert.scss  # Alert banner
        │   ├── _rooms.scss  # Room grid, cards, seats
        │   ├── _auth.scss   # Auth card, auth links
        │   ├── _footer.scss # Footer, dev links
        │   ├── _games.scss  # Game history cards
        │   └── _animations.scss # Keyframe animations
        ├── _melds.scss      # Meld component styles (upright, sideways, stacked)
        ├── _hand.scss       # Hand component styles (tile row, drawn tile gap)
        ├── _discards.scss   # Discard component styles (rows, grayed, sideways riichi)
        ├── _room.scss       # Room page styles (players, chat)
        └── _game.scss       # Game client styles (log panel, status badges)
```

## Dependencies

### Runtime
- `lit-html` (3.3) — Lightweight HTML template rendering (no virtual DOM)
- `@msgpack/msgpack` (3.1) — MessagePack encode/decode for game server communication
- `@picocss/pico` (2.1) — Classless CSS framework with dark theme support
- `zod` — Runtime schema validation for wire protocol message parsing

### Development
- `vite` (6.x) — Build tool and HMR dev server
- `sass` (1.97) — Dart Sass SCSS compiler (Vite peer dependency)
- `typescript` (5.9) — TypeScript compiler (type checking only; Vite handles bundling)
- `svgo` (4.x) — SVG optimizer for tile sprite generation
- `oxlint` — Fast JavaScript/TypeScript linter
- `oxfmt` — Code formatter
- `stylelint` + `stylelint-config-standard-scss` — SCSS linter
