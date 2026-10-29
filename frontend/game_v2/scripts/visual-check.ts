import { readFile, readdir, rm } from "node:fs/promises";
import { type IncomingMessage, type Server, type ServerResponse, createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { parseArgs } from "node:util";

import { encode } from "@msgpack/msgpack";
import {
    type Browser,
    type BrowserContext,
    type BrowserContextOptions,
    type BrowserType,
    type Page,
    chromium,
    devices,
    webkit,
} from "playwright";

/**
 * The v2 client's layout gate. It builds nothing itself: it serves the built `dist/` (the app page for every
 * `/play/` path, as the lobby does), a replay fixture under the replay API and a seat transcript over a mocked
 * game socket, then loads every storybook page, the replay and the live game at each viewport and asserts what a
 * player would see: content visible, nothing overlapping, everything inside the board and the screen, readable
 * text and tappable tiles. Any console error, failed request or missing element fails it. It writes a screenshot
 * of each page for review.
 */

const APP_ROOT = resolve(import.meta.dirname, "..");
const DIST = join(APP_ROOT, "dist");
const DEFAULT_SHOTS = resolve(APP_ROOT, "../../thoughts/screenshots/visual-check");
const ASSET_PREFIX = "/game-assets/v2/";
const REPLAY_FIXTURE = join(APP_ROOT, "tests/fixtures/replays/four_kans.txt");
/** The largest engine replay fixture, which the replay load budget reads. */
const BUDGET_REPLAY_FIXTURE = join(APP_ROOT, "tests/fixtures/replays/full_game.txt");
const BUDGET_GAME_ID = "load-budget";
const TRANSCRIPT_FIXTURE = join(APP_ROOT, "src/fixtures/seat-scenarios/call_prompt_seat_1.json");
/** The transcript's labels the live game is stopped at: its call prompt's buttons, and its turn after the chi. */
const LIVE_CHECKPOINTS = ["prompt", "turn"] as const;
const GAME_ID = "visual-check";

/** The smallest local hand tile a landscape table may draw on a supported size, in CSS pixels: a tap target. */
const MIN_TAP_WIDTH = 32;
const MIN_TAP_HEIGHT = 42;
/** The smallest decision button, in CSS pixels: a tap target. */
const MIN_ACTION_SIZE = 40;
/** The smallest computed font size of the board's centre text and dora label, in CSS pixels. */
const MIN_TEXT_PX = 10;
/** Sub-pixel slack for comparing layout boxes. */
const EPSILON = 1;
const REPLAY_MAX_STEPS = 300;
const REPLAY_LOCAL_MELDS = 2;
const SETTLE_MS = 150;
const SELECTOR_TIMEOUT_MS = 5000;
/** Pages a browser checks at once, each in its own context. */
const PAGES_AT_ONCE = 6;
/**
 * The replay load budget: reading the largest replay fixture (parse, reduce into the client timeline, steps and
 * navigation index), measured by the replay view's `replay-load` User Timing on Chromium slowed to a low-end phone's
 * CPU, the median of a few loads. Measured 2026-10-29 on a 12-core dev host: 12 ms unthrottled, 40 ms at 4x, 69 ms
 * at 6x; the budget leaves room for a slower host, not for a slower reader.
 */
const LOAD_CPU_SLOWDOWN = 6;
const LOAD_RUNS = 3;
const LOAD_BUDGET_MS = 120;
const LOAD_MEASURE = "replay-load";
/** What reading the whole fixture yields, which every timed load must report before its time counts. */
const LOAD_EXPECTED = {
    parseErrors: 0,
    rounds: 12,
    standings: [
        [3, 25_000],
        [0, 25_000],
        [1, 25_000],
        [2, 25_000],
    ],
    steps: 1694,
};

const CONTENT_TYPES: Readonly<Record<string, string>> = {
    ".css": "text/css",
    ".html": "text/html",
    ".js": "text/javascript",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
};

/** Safe-area insets to emulate, which Playwright reports as zero: set through the theme's `--ronin-safe-*`. */
interface Insets {
    readonly left: number;
    readonly right: number;
    readonly bottom: number;
}

interface Viewport {
    readonly name: string;
    readonly engine: BrowserType;
    readonly context: BrowserContextOptions;
    readonly portrait: boolean;
    /** The live game shows its rotate panel here (an upright phone). */
    readonly rotates: boolean;
    /** A supported device size, where the tap minimum holds and the round end fits without scrolling. */
    readonly supported: boolean;
    readonly insets?: Insets;
}

interface Required {
    /** Selectors that must match an element a player can see. */
    readonly visible: readonly string[];
    /** Selectors that must match an element, shown or not (the game's hidden half of its rotate split). */
    readonly attached?: readonly string[];
}

type PageKind =
    | { readonly kind: "document" }
    | { readonly kind: "board"; readonly prepare?: (page: Page) => Promise<void> }
    | { readonly kind: "panel"; readonly countdown: boolean }
    | { readonly kind: "game"; readonly checkpoint: (typeof LIVE_CHECKPOINTS)[number] };

type PageCase = PageKind & {
    readonly name: string;
    readonly path: string;
    readonly required: Required;
};

interface Box {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}

interface Size {
    readonly width: number;
    readonly height: number;
}

/** A box on the board and the area it belongs to; boxes of different areas must not intersect. */
interface GroupedBox {
    readonly group: string;
    readonly box: Box;
}

interface BoardMeasure {
    readonly board: Box;
    readonly boardScroll: Size;
    readonly boardClient: Size;
    readonly aside: { readonly box: Box; readonly scroll: Size; readonly overflowY: string } | null;
    readonly overlay: { readonly box: Box; readonly scroll: Size; readonly client: Size } | null;
    readonly tiles: readonly Box[];
    readonly hiddenTiles: number;
    readonly grouped: readonly GroupedBox[];
    readonly localTiles: readonly Box[];
    readonly actions: readonly Box[];
    readonly fonts: readonly { readonly name: string; readonly px: number }[];
    readonly centerTexts: readonly GroupedBox[];
}

interface PageMeasure {
    readonly innerWidth: number;
    readonly innerHeight: number;
    readonly scrollWidth: number;
    readonly scrollHeight: number;
}

/** What one page's checks found: the failures, and how many checks ran so a page that checked nothing fails. */
class PageReport {
    readonly failures: string[] = [];
    checks = 0;
    summary = "";

    expect(ok: boolean, failure: string): void {
        this.checks += 1;
        if (!ok) {
            this.failures.push(failure);
        }
    }
}

/** One page under check: the viewport it was loaded at, what its document measured, and its report. */
interface PageRun {
    readonly page: Page;
    readonly viewport: Viewport;
    readonly measure: PageMeasure;
    readonly report: PageReport;
}

/** The fixture server's origin and, for each live checkpoint, the socket frames its mocked game server sends. */
interface Fixtures {
    readonly origin: string;
    readonly frames: ReadonlyMap<string, readonly Uint8Array[]>;
}

function deviceOptions(name: string): BrowserContextOptions {
    const { defaultBrowserType: _engine, ...options } = devices[name];
    return options;
}

/**
 * The acceptance viewports: a desktop, the upright phone that gets the rotate panel, the notched landscape phone
 * (its insets cover the plain one), and the smallest supported landscape, which also keeps the aside's scroll honest.
 */
const VIEWPORTS: readonly Viewport[] = [
    {
        context: { viewport: { height: 800, width: 1280 } },
        engine: chromium,
        name: "desktop",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13"),
        engine: webkit,
        name: "phone-portrait",
        portrait: true,
        rotates: true,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13 landscape"),
        engine: webkit,
        insets: { bottom: 21, left: 47, right: 47 },
        name: "phone-notch-landscape",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone SE (3rd gen) landscape"),
        engine: webkit,
        name: "phone-se-landscape",
        portrait: false,
        rotates: false,
        supported: true,
    },
];

const BOARD_VISIBLE = [
    ".game-board .board-table .tile",
    ".board-local .board-area--bottom-hand .tile",
];

function boardCase(name: string, query: string, extra: readonly string[] = []): PageCase {
    return {
        kind: "board",
        name,
        path: `/play/storybook/board${query}`,
        prepare: hideBoardDebug,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

/** A round result over the board storybook's board, one of its result stories, at a page of it. */
function resultCase(result: string, query: string, extra: readonly string[]): PageCase {
    return boardCase(
        `board-result-${result.replaceAll("_", "-")}`,
        `?overlay=round_end&result=${result}${query}`,
        [".board-overlay__panel", ...extra],
    );
}

/** A decisions story: the live board at a checkpoint of a generated seat transcript. */
function decisionCase(story: string, extra: readonly string[]): PageCase {
    return {
        kind: "board",
        name: `decisions-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/decisions?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

const ACTION = ".board-actions .decision-controls__action";

function documentCase(name: string, path: string, content: string): PageCase {
    return { kind: "document", name, path, required: { visible: [content] } };
}

const PAGES: readonly PageCase[] = [
    documentCase("storybook", "/play/storybook", ".storybook .tile"),
    documentCase("storybook-hand", "/play/storybook/hand", ".storybook .hand .tile"),
    documentCase("storybook-discards", "/play/storybook/discards", ".storybook .discards .tile"),
    documentCase("storybook-melds", "/play/storybook/melds", ".storybook .meld .tile"),
    boardCase("board-full-rivers", "?state=full_rivers"),
    boardCase("board-worst", "?state=worst", [".board-strip .meld", ".board-dora .tile"]),
    resultCase("double_ron", "&page=1", [".round-end-result__pager"]),
    resultCase("sanbaiman", "", [".round-end-result__hand .meld"]),
    resultCase("pao", "", [".round-end-result__notes"]),
    resultCase("exhaustive", "", [".round-end-result__tenpai .tile"]),
    decisionCase("call_prompt", [ACTION, ".decision-controls__countdown"]),
    decisionCase("chankan_prompt", [ACTION, ".board-strip .meld"]),
    decisionCase("riichi_pick", [`${ACTION}[aria-pressed="true"]`, ".hand-tile--disabled"]),
    decisionCase("riichi_turn", [ACTION, ".decision-controls__furiten", ".hand-tile--selectable"]),
    decisionCase("answered", [".hand-tile--selected"]),
    decisionCase("round_end", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("double_ron_first", [".round-end-result__pager", ".round-end-result__confirm"]),
    decisionCase("waiting", [".round-end-result__waiting"]),
    decisionCase("reconnect_owed", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("last_result", [".round-end-result__confirm"]),
    {
        countdown: false,
        kind: "panel",
        name: "rotate-waiting",
        path: "/play/storybook/rotate?state=waiting",
        required: { visible: [".rotate-panel", ".rotate-panel .connection-status"] },
    },
    {
        countdown: true,
        kind: "panel",
        name: "rotate-countdown",
        path: "/play/storybook/rotate?state=countdown",
        required: { visible: [".rotate-panel", ".rotate-panel__seconds"] },
    },
    {
        kind: "board",
        name: "replay",
        path: `/play/history/${GAME_ID}`,
        prepare: stepReplayToLocalMelds,
        required: { visible: [...BOARD_VISIBLE, ".board-local .meld", ".replay-controls"] },
    },
    {
        checkpoint: "prompt",
        kind: "game",
        name: "game-prompt",
        path: `/play/${GAME_ID}`,
        required: {
            attached: [
                ".game__rotate .rotate-panel__seconds",
                ".game__play .decision-controls__action",
                ".game__play .decision-controls__countdown",
            ],
            visible: [],
        },
    },
    {
        checkpoint: "turn",
        kind: "game",
        name: "game-turn",
        path: `/play/${GAME_ID}`,
        required: {
            attached: [
                ".game__rotate .rotate-panel__seconds",
                ".game__play .board-local .hand-tile--selectable",
                ".game__play .decision-controls__countdown",
            ],
            visible: [],
        },
    },
];

function contains(outer: Box, inner: Box): boolean {
    return (
        inner.left >= outer.left - EPSILON &&
        inner.top >= outer.top - EPSILON &&
        inner.left + inner.width <= outer.left + outer.width + EPSILON &&
        inner.top + inner.height <= outer.top + outer.height + EPSILON
    );
}

function intersects(first: Box, second: Box): boolean {
    return (
        first.left + EPSILON < second.left + second.width &&
        second.left + EPSILON < first.left + first.width &&
        first.top + EPSILON < second.top + second.height &&
        second.top + EPSILON < first.top + first.height
    );
}

function describeSize(size: Size): string {
    return `${Math.round(size.width)}x${Math.round(size.height)}`;
}

function describeBox(box: Box): string {
    return `${describeSize(box)}@${Math.round(box.left)},${Math.round(box.top)}`;
}

/** The board storybook opens with its debug outlines; the check measures the board a player sees. */
async function hideBoardDebug(page: Page): Promise<void> {
    await page.locator(".board-storybook__btn", { hasText: "Debug" }).click();
    if ((await page.locator(".game-board--debug").count()) !== 0) {
        throw new Error("the board storybook kept its debug outlines");
    }
}

async function stepReplayToLocalMelds(page: Page): Promise<void> {
    await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS });
    for (let step = 0; step < REPLAY_MAX_STEPS; step += 1) {
        if ((await page.locator(".board-local .meld").count()) >= REPLAY_LOCAL_MELDS) {
            return;
        }
        await page.keyboard.press("ArrowRight");
    }
    throw new Error(`the replay never showed ${REPLAY_LOCAL_MELDS} local melds`);
}

interface ReceivedEvent {
    readonly kind: "received";
    readonly label?: string;
    readonly payload: Readonly<Record<string, unknown>>;
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isReceivedEvent(event: unknown): event is ReceivedEvent {
    return isRecord(event) && event.kind === "received" && isRecord(event.payload);
}

/**
 * For each live checkpoint, the frames the server sent the transcript's seat up to the message it labels,
 * MessagePack-encoded.
 */
async function transcriptFrames(): Promise<ReadonlyMap<string, readonly Uint8Array[]>> {
    const transcript: unknown = JSON.parse(await readFile(TRANSCRIPT_FIXTURE, "utf8"));
    if (!isRecord(transcript) || !Array.isArray(transcript.events)) {
        throw new Error(`${TRANSCRIPT_FIXTURE} has no event list`);
    }
    const received = transcript.events.filter(isReceivedEvent);
    return new Map(
        LIVE_CHECKPOINTS.map((label) => {
            const last = received.findIndex((event) => event.label === label);
            if (last === -1) {
                throw new Error(`${TRANSCRIPT_FIXTURE} has no message labelled ${label}`);
            }
            return [label, received.slice(0, last + 1).map((event) => encode(event.payload))];
        }),
    );
}

function assetPath(pathname: string): string | null {
    const file = resolve(DIST, `.${pathname.slice(ASSET_PREFIX.length - 1)}`);
    return file.startsWith(DIST + sep) ? file : null;
}

async function respond(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const { pathname } = new URL(request.url ?? "/", "http://visual-check");
    let file: string | null = null;
    if (pathname.startsWith(ASSET_PREFIX)) {
        file = assetPath(pathname);
    } else if (pathname === `/api/replays/${BUDGET_GAME_ID}`) {
        file = BUDGET_REPLAY_FIXTURE;
    } else if (pathname.startsWith("/api/replays/")) {
        file = REPLAY_FIXTURE;
    } else if (pathname.startsWith("/play/")) {
        file = join(DIST, "index.html");
    }
    if (file === null) {
        response.writeHead(404).end();
        return;
    }
    try {
        const body = await readFile(file);
        const type = CONTENT_TYPES[extname(file)] ?? "text/plain";
        response.writeHead(200, { "Content-Type": type }).end(body);
    } catch {
        response.writeHead(404).end();
    }
}

async function startServer(): Promise<{ server: Server; origin: string }> {
    const server = createServer((request, response) => {
        void respond(request, response);
    });
    await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
    const address = server.address();
    if (address === null || typeof address === "string") {
        throw new Error("the fixture server has no TCP port");
    }
    return { origin: `http://127.0.0.1:${address.port}`, server };
}

/** A context that keeps the run offline and deterministic: no web fonts, the handoff set, the socket mocked. */
async function openContext(
    browser: Browser,
    viewport: Viewport,
    { frames, origin }: { readonly frames: readonly Uint8Array[]; readonly origin: string },
): Promise<BrowserContext> {
    const context = await browser.newContext(viewport.context);
    await context.route(
        (url) => url.origin !== origin,
        (route) => route.fulfill({ body: "", contentType: "text/css", status: 200 }),
    );
    const wsUrl = `${origin.replace("http", "ws")}/ws/${GAME_ID}`;
    const handoff = JSON.stringify({ gameTicket: "visual-check", wsUrl });
    await context.addInitScript(([key, value]) => sessionStorage.setItem(key, value), [
        `game_session:${GAME_ID}`,
        handoff,
    ] as const);
    await context.routeWebSocket(wsUrl, (socket) => {
        let joined = false;
        socket.onMessage(() => {
            if (joined) {
                return;
            }
            joined = true;
            for (const frame of frames) {
                socket.send(Buffer.from(frame));
            }
        });
    });
    return context;
}

async function emulateInsets(page: Page, insets: Insets | undefined): Promise<void> {
    if (insets === undefined) {
        return;
    }
    const { bottom, left, right } = insets;
    await page.addStyleTag({
        content: `:root { --ronin-safe-left: ${left}px; --ronin-safe-right: ${right}px; --ronin-safe-bottom: ${bottom}px; }`,
    });
}

function measurePage(page: Page): Promise<PageMeasure> {
    return page.evaluate(() => ({
        innerHeight: window.innerHeight,
        innerWidth: window.innerWidth,
        scrollHeight: document.documentElement.scrollHeight,
        scrollWidth: document.documentElement.scrollWidth,
    }));
}

/** Every element `selector` matches must be shown (not hidden, transparent or zero-sized), and one must match. */
function countHidden(page: Page, selector: string): Promise<{ matched: number; hidden: number }> {
    return page.evaluate((query) => {
        const elements = [...document.querySelectorAll(query)];
        const hidden = elements.filter((element) => {
            const rect = element.getBoundingClientRect();
            const shown = element.checkVisibility({
                opacityProperty: true,
                visibilityProperty: true,
            });
            return !shown || rect.width === 0 || rect.height === 0;
        });
        return { hidden: hidden.length, matched: elements.length };
    }, selector);
}

async function checkVisible(
    page: Page,
    selectors: readonly string[],
    report: PageReport,
): Promise<void> {
    for (const selector of selectors) {
        const { hidden, matched } = await countHidden(page, selector);
        report.expect(matched > 0, `nothing matches ${selector}`);
        report.expect(hidden === 0, `${hidden} of ${matched} ${selector} hidden or empty`);
    }
}

function measureBoard(page: Page): Promise<BoardMeasure> {
    return page.evaluate(({ centerTextSelectors, fontSelectors }) => {
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function box(element: Element): Box {
            const rect = element.getBoundingClientRect();
            return {
                height: rect.height,
                left: rect.left + window.scrollX,
                top: rect.top + window.scrollY,
                width: rect.width,
            };
        }
        const board = document.querySelector(".game-board");
        if (board === null) {
            throw new Error("no .game-board");
        }
        const tableTiles = [...board.querySelectorAll(".tile")].filter(
            (tile) => tile.closest(".board-overlay") === null,
        );
        const grouped: GroupedBox[] = [];
        for (const tile of tableTiles) {
            const area = tile.closest("[data-area], .board-dora");
            grouped.push({ box: box(tile), group: area?.getAttribute("data-area") ?? "dora" });
        }
        for (const center of board.querySelectorAll(".board-center")) {
            grouped.push({ box: box(center), group: "center" });
        }
        for (const dora of board.querySelectorAll(".board-dora")) {
            grouped.push({ box: box(dora), group: "dora" });
        }
        const decisionActions = [
            ...board.querySelectorAll(".board-actions .decision-controls__action"),
        ].map(box);
        for (const action of decisionActions) {
            grouped.push({ box: action, group: "actions" });
        }
        const resultActions = [
            ...board.querySelectorAll(".board-overlay .round-end-result__confirm"),
        ].map(box);
        const actions = [...decisionActions, ...resultActions];
        const aside = document.querySelector(".board-page__aside");
        const overlay = board.querySelector(".board-overlay__panel");
        const centerTexts = [...board.querySelectorAll(centerTextSelectors)].map(
            (element, index) => ({
                box: box(element),
                group: `${element.className.split(" ")[0]}#${index}`,
            }),
        );
        const fonts = [...board.querySelectorAll(fontSelectors)].map((element) => ({
            name: element.className.split(" ")[0],
            px: Number.parseFloat(getComputedStyle(element).fontSize),
        }));
        return {
            actions,
            aside:
                aside === null
                    ? null
                    : {
                          box: box(aside),
                          overflowY: getComputedStyle(aside).overflowY,
                          scroll: { height: aside.scrollHeight, width: aside.scrollWidth },
                      },
            board: box(board),
            boardClient: { height: board.clientHeight, width: board.clientWidth },
            boardScroll: { height: board.scrollHeight, width: board.scrollWidth },
            centerTexts,
            fonts,
            grouped,
            hiddenTiles: tableTiles.filter(
                (tile) =>
                    !tile.checkVisibility({ opacityProperty: true, visibilityProperty: true }),
            ).length,
            localTiles: [
                ...board.querySelectorAll(".board-local .board-area--bottom-hand .tile"),
            ].map(box),
            overlay:
                overlay === null
                    ? null
                    : {
                          box: box(overlay),
                          client: { height: overlay.clientHeight, width: overlay.clientWidth },
                          scroll: { height: overlay.scrollHeight, width: overlay.scrollWidth },
                      },
            tiles: tableTiles.map(box),
        };
    }, BOARD_TEXT);
}

/** The text whose size has a floor, and the centre's pieces of text, which must not overlap one another. */
const BOARD_TEXT = {
    centerTextSelectors: [
        ".board-center__points",
        ".board-center__round",
        ".board-center__wall",
        ".board-center__stick",
        ".board-center__wind-badge",
        ".board-center__riichi-stick",
    ].join(", "),
    fontSelectors: [
        ".board-center__round",
        ".board-center__sticks",
        ".board-center__points",
        ".board-center__mark",
        ".board-dora__label",
    ].join(", "),
} as const;

function viewportBox(page: Page): Promise<Box> {
    return page.evaluate(() => ({
        height: window.innerHeight,
        left: window.scrollX,
        top: window.scrollY,
        width: window.innerWidth,
    }));
}

/** Pairs of boxes from different areas that intersect, named by their areas. */
function findOverlaps(grouped: readonly GroupedBox[]): string[] {
    const overlaps = new Set<string>();
    for (const [index, first] of grouped.entries()) {
        for (const second of grouped.slice(index + 1)) {
            if (first.group !== second.group && intersects(first.box, second.box)) {
                overlaps.add([first.group, second.group].toSorted().join(" x "));
            }
        }
    }
    return [...overlaps];
}

function checkBoardContent(board: BoardMeasure, report: PageReport): void {
    const { boardClient: client, boardScroll: scroll } = board;
    report.expect(
        scroll.width <= client.width + EPSILON && scroll.height <= client.height + EPSILON,
        `board content overflows its box: scroll ${describeSize(scroll)} > client ${describeSize(client)}`,
    );
    report.expect(
        board.tiles.length > 0 && board.hiddenTiles === 0,
        `${board.hiddenTiles} hidden tile(s)`,
    );
    const outside = board.tiles.filter((tile) => !contains(board.board, tile));
    report.expect(outside.length === 0, `${outside.length} tile(s) outside the board`);
    const overlaps = findOverlaps(board.grouped);
    report.expect(overlaps.length === 0, `areas overlap: ${overlaps.join(", ")}`);

    const small = board.fonts.filter((font) => font.px < MIN_TEXT_PX);
    report.expect(board.fonts.length > 0, "no centre text measured");
    report.expect(
        small.length === 0,
        `text under ${MIN_TEXT_PX}px: ${small.map((font) => `${font.name} ${font.px}px`).join(", ")}`,
    );
}

function checkAside(board: BoardMeasure, frame: Box, report: PageReport): void {
    const { aside } = board;
    if (aside === null) {
        return;
    }
    report.expect(!intersects(aside.box, board.board), "the aside overlaps the board");
    report.expect(
        contains(frame, aside.box),
        `the aside ${describeBox(aside.box)} leaves the page`,
    );
    const scrolls = aside.scroll.height > aside.box.height + EPSILON;
    report.expect(
        !scrolls || aside.overflowY === "auto" || aside.overflowY === "scroll",
        "the aside's controls overflow it with no way to scroll to them",
    );
}

function checkOverlay(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { overlay } = board;
    if (overlay === null) {
        return;
    }
    report.expect(contains(board.board, overlay.box), "the overlay panel leaves the board");
    if (viewport.supported) {
        report.expect(
            overlay.scroll.height <= overlay.client.height + EPSILON &&
                overlay.scroll.width <= overlay.client.width + EPSILON,
            `the overlay panel's content overflows it: ${describeSize(overlay.scroll)} > ${describeSize(overlay.client)}`,
        );
    }
}

function checkLocalHand(board: BoardMeasure, screen: Box, report: PageReport): void {
    const hidden = board.localTiles.filter((tile) => !contains(screen, tile));
    report.expect(hidden.length === 0, `${hidden.length} local hand tile(s) outside the viewport`);
    const small = board.localTiles.filter(
        (tile) => tile.width < MIN_TAP_WIDTH - EPSILON || tile.height < MIN_TAP_HEIGHT - EPSILON,
    );
    report.expect(
        small.length === 0,
        `local hand tiles under ${MIN_TAP_WIDTH}x${MIN_TAP_HEIGHT}: ${small.map(describeBox).join(", ")}`,
    );
}

/** Decision buttons and a round result's confirm sit wholly on the board and the screen, large enough to tap. */
function checkActions(board: BoardMeasure, screen: Box, report: PageReport): void {
    const outside = board.actions.filter(
        (action) => !contains(board.board, action) || !contains(screen, action),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} decision button(s) off the board or screen`,
    );
    const small = board.actions.filter(
        (action) =>
            action.width < MIN_ACTION_SIZE - EPSILON || action.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `decision buttons under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
}

function describeLocalTile(tiles: readonly Box[]): string {
    const [tile] = tiles;
    return tile ? `${tile.width.toFixed(1)}x${tile.height.toFixed(1)}` : "none";
}

async function checkBoard({ measure, page, report, viewport }: PageRun): Promise<string> {
    const board = await measureBoard(page);
    const screen = await viewportBox(page);
    checkBoardContent(board, report);
    if (viewport.supported) {
        const crowded = findOverlaps(board.centerTexts);
        report.expect(crowded.length === 0, `centre pieces overlap: ${crowded.join(", ")}`);
    }
    checkOverlay(board, viewport, report);
    const pageExtent = { height: measure.scrollHeight, left: 0, top: 0, width: measure.innerWidth };
    if (viewport.portrait) {
        report.expect(
            contains(pageExtent, board.board),
            "the board is outside the scrollable page",
        );
        checkAside(board, pageExtent, report);
    } else {
        report.expect(
            contains(screen, board.board),
            `the board ${describeBox(board.board)} leaves the viewport`,
        );
        checkAside(board, screen, report);
    }
    if (viewport.supported && !viewport.portrait) {
        checkLocalHand(board, screen, report);
        checkActions(board, screen, report);
    }
    const fonts = Math.min(...board.fonts.map((font) => font.px));
    const scroll = `scroll ${describeSize(board.boardScroll)}`;
    const actions = board.actions.length === 0 ? "" : `, ${board.actions.length} button(s)`;
    return `board ${describeSize(board.boardClient)} ${scroll}, local tile ${describeLocalTile(board.localTiles)}${actions}, min text ${fonts}px`;
}

async function isShown(page: Page, selector: string): Promise<boolean> {
    return page.locator(selector).first().isVisible();
}

async function checkPanel(page: Page, countdown: boolean, report: PageReport): Promise<string> {
    await checkVisible(page, [".rotate-panel__title", ".rotate-panel__leave"], report);
    const seconds = page.locator(".rotate-panel__seconds");
    report.expect(
        (await seconds.count()) === (countdown ? 1 : 0),
        countdown ? "no countdown on the panel" : "a countdown on a panel with no decision",
    );
    return countdown ? `countdown ${await seconds.first().textContent()}` : "no countdown";
}

async function checkGame(run: PageRun): Promise<string> {
    const { measure, page, report, viewport } = run;
    const seconds = Number(
        await page.locator(".game__rotate .rotate-panel__seconds").textContent(),
    );
    report.expect(seconds > 0, `the open decision's countdown reads ${seconds}`);
    const { rotates } = viewport;
    report.expect(
        (await isShown(page, ".game__rotate")) === rotates,
        rotates ? "the rotate panel is hidden on an upright phone" : "the rotate panel shows",
    );
    report.expect(
        (await isShown(page, ".game__play")) === !rotates,
        rotates ? "the table shows on an upright phone" : "the table is hidden",
    );
    if (!rotates) {
        await checkVisible(
            page,
            [...BOARD_VISIBLE, ".game__play .decision-controls__countdown"],
            report,
        );
        return `countdown ${seconds}, ${await checkBoard(run)}`;
    }
    await checkVisible(
        page,
        [".game__rotate .rotate-panel__seconds", ".game__rotate .rotate-panel__leave"],
        report,
    );
    const panel = await page.evaluate(() => {
        const element = document.querySelector(".game__rotate");
        if (element === null) {
            return null;
        }
        const { height, left, top, width } = element.getBoundingClientRect();
        return {
            clientHeight: element.clientHeight,
            rect: { height, left, top, width },
            scrollHeight: element.scrollHeight,
        };
    });
    report.expect(panel !== null, "no .game__rotate");
    if (panel !== null) {
        const screen = { height: measure.innerHeight, left: 0, top: 0, width: measure.innerWidth };
        report.expect(
            contains(panel.rect, screen) && contains(screen, panel.rect),
            `the rotate panel ${describeBox(panel.rect)} does not cover the viewport`,
        );
        report.expect(
            panel.scrollHeight <= panel.clientHeight + EPSILON,
            "the rotate panel's content needs scrolling",
        );
    }
    return `countdown ${seconds}, rotate panel shown`;
}

async function checkPage(
    { page, report, viewport }: Omit<PageRun, "measure">,
    pageCase: PageCase,
): Promise<string> {
    const measure = await measurePage(page);
    const run = { measure, page, report, viewport };
    report.expect(
        measure.scrollWidth <= measure.innerWidth,
        `horizontal page overflow: ${measure.scrollWidth} > ${measure.innerWidth}`,
    );
    await checkVisible(page, pageCase.required.visible, report);
    switch (pageCase.kind) {
        case "document": {
            return `page ${measure.scrollWidth}x${measure.scrollHeight}`;
        }
        case "board": {
            return checkBoard(run);
        }
        case "panel": {
            return checkPanel(page, pageCase.countdown, report);
        }
        case "game": {
            return checkGame(run);
        }
    }
}

interface PageLoad {
    readonly context: BrowserContext;
    readonly viewport: Viewport;
    readonly origin: string;
    readonly shots: string;
}

async function loadPage(page: Page, pageCase: PageCase, origin: string): Promise<void> {
    await page.goto(origin + pageCase.path);
    if (pageCase.kind === "board" && pageCase.prepare) {
        await pageCase.prepare(page);
    }
    const { attached = [], visible } = pageCase.required;
    for (const selector of visible) {
        await page.waitForSelector(selector, { state: "visible", timeout: SELECTOR_TIMEOUT_MS });
    }
    for (const selector of attached) {
        await page.waitForSelector(selector, { state: "attached", timeout: SELECTOR_TIMEOUT_MS });
    }
}

async function runPage(
    { context, origin, shots, viewport }: PageLoad,
    pageCase: PageCase,
): Promise<PageReport> {
    const report = new PageReport();
    const page = await context.newPage();
    page.on("console", (message) => {
        if (message.type() === "error") {
            report.failures.push(`console error: ${message.text()}`);
        }
    });
    page.on("pageerror", (error) => report.failures.push(`page error: ${error.message}`));
    page.on("requestfailed", (request) => report.failures.push(`request failed: ${request.url()}`));
    try {
        await loadPage(page, pageCase, origin);
        await emulateInsets(page, viewport.insets);
        await page.evaluate(() => document.fonts.ready.then(() => undefined));
        await page.waitForTimeout(SETTLE_MS);
        report.summary = await checkPage({ page, report, viewport }, pageCase);
        await page.screenshot({ path: join(shots, `${viewport.name}-${pageCase.name}.png`) });
    } catch (error: unknown) {
        report.failures.push(error instanceof Error ? error.message : String(error));
    } finally {
        await page.close();
    }
    if (report.checks === 0 && report.failures.length === 0) {
        report.failures.push("no check ran");
    }
    return report;
}

/** One page at one viewport, checked in a context of its own, its findings named by both. */
interface PageTask {
    readonly viewport: Viewport;
    readonly pageCase: PageCase;
}

interface TaskResult {
    readonly name: string;
    readonly report: PageReport;
}

async function runTask(
    browser: Browser,
    { pageCase, viewport }: PageTask,
    { fixtures, shots }: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult> {
    const frames = pageCase.kind === "game" ? fixtures.frames.get(pageCase.checkpoint) : [];
    const context = await openContext(browser, viewport, {
        frames: frames ?? [],
        origin: fixtures.origin,
    });
    try {
        const report = await runPage(
            { context, origin: fixtures.origin, shots, viewport },
            pageCase,
        );
        return { name: `${viewport.name} ${pageCase.name}`, report };
    } finally {
        await context.close();
    }
}

/** Run `tasks` with at most `limit` at once, keeping their order in the results. */
async function runPooled<Task, Result>(
    tasks: readonly Task[],
    limit: number,
    run: (task: Task) => Promise<Result>,
): Promise<Result[]> {
    const results: Result[] = [];
    let next = 0;
    async function worker(): Promise<void> {
        for (let index = next++; index < tasks.length; index = next++) {
            results[index] = await run(tasks[index]);
        }
    }
    await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, worker));
    return results;
}

/** Check every page at each of an engine's viewports in one browser, several pages at once. */
async function runEngine(
    browser: Browser,
    viewports: readonly Viewport[],
    run: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult[]> {
    const tasks = viewports.flatMap((viewport) =>
        PAGES.map((pageCase) => ({ pageCase, viewport })),
    );
    return runPooled(tasks, PAGES_AT_ONCE, (task) => runTask(browser, task, run));
}

function median(values: readonly number[]): number {
    const sorted = values.toSorted((left, right) => left - right);
    return sorted[Math.floor(sorted.length / 2)];
}

/** One load's timing and what the replay view says it read, from its `replay-load` measure. */
interface LoadRun {
    readonly ms: number;
    readonly detail: unknown;
}

/** One load of the largest replay on a slowed CPU: the view's `replay-load` measure. */
async function measureReplayLoad(browser: Browser, origin: string): Promise<LoadRun> {
    const context = await openContext(browser, VIEWPORTS[0], { frames: [], origin });
    try {
        const page = await context.newPage();
        const cdp = await context.newCDPSession(page);
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: LOAD_CPU_SLOWDOWN });
        await page.goto(`${origin}/play/history/${BUDGET_GAME_ID}`);
        await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS * 2 });
        return await page.evaluate((name) => {
            const [entry] = performance.getEntriesByName(name, "measure");
            return entry instanceof PerformanceMeasure
                ? { detail: entry.detail, ms: entry.duration }
                : { detail: null, ms: Number.NaN };
        }, LOAD_MEASURE);
    } finally {
        await context.close();
    }
}

/** Why a load's timing does not count: it read something other than the whole fixture, or recorded no time. */
function invalidLoad({ detail, ms }: LoadRun): string | null {
    if (JSON.stringify(detail) !== JSON.stringify(LOAD_EXPECTED)) {
        return `read ${JSON.stringify(detail)}, not the fixture's ${JSON.stringify(LOAD_EXPECTED)}`;
    }
    return Number.isFinite(ms) && ms > 0 ? null : `recorded no time (${ms})`;
}

async function checkReplayLoad(browser: Browser, origin: string): Promise<string[]> {
    const runs: LoadRun[] = [];
    for (let run = 0; run < LOAD_RUNS; run += 1) {
        runs.push(await measureReplayLoad(browser, origin));
    }
    const invalid = runs.flatMap((run) => invalidLoad(run) ?? []);
    if (invalid.length > 0) {
        return invalid.map((reason) => `replay load: a run ${reason}`);
    }
    const typical = median(runs.map((run) => run.ms));
    const shown = runs.map((run) => run.ms.toFixed(0)).join(", ");
    console.info(
        `replay load at ${LOAD_CPU_SLOWDOWN}x CPU slowdown: median ${typical.toFixed(0)} ms (${shown}), budget ${LOAD_BUDGET_MS} ms`,
    );
    return typical > LOAD_BUDGET_MS
        ? [`replay load: median ${typical.toFixed(0)} ms over the ${LOAD_BUDGET_MS} ms budget`]
        : [];
}

function reportFailures(results: readonly TaskResult[]): string[] {
    return results.flatMap(({ name, report }) => {
        if (report.summary !== "") {
            console.info(`${name}: ${report.summary}`);
        }
        return report.failures.map((failure) => `${name}: ${failure}`);
    });
}

function viewportsOf(engine: BrowserType): Viewport[] {
    return VIEWPORTS.filter((viewport) => viewport.engine === engine);
}

/** Both engines' pages at once, then the replay load budget on the Chromium browser, the CPU otherwise idle. */
async function checkAll(fixtures: Fixtures, shots: string): Promise<string[]> {
    const [chromiumBrowser, webkitBrowser] = await Promise.all([
        chromium.launch(),
        webkit.launch(),
    ]);
    try {
        const run = { fixtures, shots };
        const results = await Promise.all([
            runEngine(chromiumBrowser, viewportsOf(chromium), run),
            runEngine(webkitBrowser, viewportsOf(webkit), run),
        ]);
        const pageFailures = reportFailures(results.flat());
        return [...pageFailures, ...(await checkReplayLoad(chromiumBrowser, fixtures.origin))];
    } finally {
        await Promise.all([chromiumBrowser.close(), webkitBrowser.close()]);
    }
}

/** Remove the last run's screenshots, so the folder holds only this run's. */
async function clearShots(folder: string): Promise<void> {
    const files = await readdir(folder).catch(() => []);
    await Promise.all(
        files.filter((file) => file.endsWith(".png")).map((file) => rm(join(folder, file))),
    );
}

async function main(): Promise<number> {
    const { values } = parseArgs({
        options: { shots: { default: DEFAULT_SHOTS, type: "string" } },
    });
    const shots = resolve(values.shots);
    if (shots === DEFAULT_SHOTS) {
        await clearShots(shots);
    }
    const frames = await transcriptFrames();
    const { origin, server } = await startServer();
    const failures = await checkAll({ frames, origin }, shots).finally(() => server.close());
    if (failures.length > 0) {
        console.error(
            `Visual check failed:\n${failures.map((failure) => `  ${failure}`).join("\n")}`,
        );
        return 1;
    }
    const pages = VIEWPORTS.length * PAGES.length;
    console.info(`Visual check passed: ${pages} pages; screenshots in ${shots}`);
    return 0;
}

process.exitCode = await main();
