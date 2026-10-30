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
const REPLAY_FIXTURE = join(APP_ROOT, "src/fixtures/replays/four_kans.txt");
/** The largest engine replay fixture, which the replay load budget reads. */
const BUDGET_REPLAY_FIXTURE = join(APP_ROOT, "src/fixtures/replays/full_game.txt");
const BUDGET_GAME_ID = "load-budget";
const TRANSCRIPT_FIXTURE = join(APP_ROOT, "src/fixtures/seat-scenarios/call_prompt_seat_1.json");
/** The transcript's labels the live game is stopped at: its call prompt's buttons, and its turn after the chi. */
const LIVE_CHECKPOINTS = ["prompt", "turn"] as const;
const GAME_ID = "visual-check";

/** The smallest local hand tile a landscape table may draw on a supported phone, in CSS pixels: a tap target. */
const MIN_TAP: Size = { height: 42, width: 32 };
/** The smallest decision button and leave button, in CSS pixels: a tap target. */
const MIN_ACTION_SIZE = 40;
/** The smallest face-up tile of another seat's hand or melds in landscape, in CSS pixels: readable at a glance. */
const MIN_OPPONENT_FACE: Size = { height: 17, width: 13 };
/** The replay aside's text on a desktop: the least font size in px and the most lines each part may wrap to. */
const REPLAY_TEXT_LIMITS: Readonly<
    Record<string, { readonly px: number; readonly lines: number }>
> = {
    incomplete: { lines: 4, px: 12 },
    narration: { lines: 3, px: 13 },
    round: { lines: 2, px: 13 },
};
/** The fewest lines of the replay's narration a landscape phone's column shows without scrolling it. */
const MIN_PHONE_NARRATION_LINES = 3;
/** A desktop river tile's long side as a share of the local hand tile's: the hierarchy the references keep. */
const RIVER_TO_HAND = { max: 0.75, min: 0.55 } as const;
/** How far a desktop side seat's hand may stand from the centre, as a share of the board's width. */
const MAX_SIDE_DISTANCE_SHARE = 0.25;
/** How close a nameplate sits to its own seat's tiles, in CSS pixels. */
const MAX_PLATE_DISTANCE = 16;
/** The centre's wall count and the sticks against the score: never under this share of its size. */
const MIN_COUNTER_TO_SCORE = 0.8;
/** The smallest computed font size of the board's centre text, dora label and nameplates, in CSS pixels. */
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
    complete: true,
    damagedLine: null,
    rounds: 12,
    standings: [
        [3, 25_000],
        [0, 25_000],
        [1, 25_000],
        [2, 25_000],
    ],
    stops: 1693,
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
    /** The smallest local hand tile it may draw in landscape: a tap target, and on a desktop a hand that fills it. */
    readonly handFloor: Size;
    /** A desktop, where the river to hand ratio and the side seats' distance from the centre hold. */
    readonly desktop: boolean;
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
    /** Every board tile but the local hand's and the decision buttons': rivers, other seats, melds, dora. */
    readonly otherTiles: readonly Box[];
    readonly actions: readonly Box[];
    /** The calls shown by their seats. */
    readonly callouts: readonly Box[];
    readonly fonts: readonly { readonly name: string; readonly px: number }[];
    readonly centerTexts: readonly GroupedBox[];
    readonly nameplates: readonly Box[];
    /** Each plate by its seat, and each seat's tiles (its hand and melds; the bottom seat's in the local strip). */
    readonly plates: readonly { readonly seat: string; readonly box: Box }[];
    readonly seatTiles: Readonly<Record<string, readonly Box[]>>;
    readonly riverTiles: readonly Box[];
    readonly opponentFaces: readonly Box[];
    readonly center: Box | null;
    readonly leave: Box | null;
    /** The page's corner on the board: the session's status and the way back, which no panel over the board covers. */
    readonly menu: readonly Box[];
    /** The replay's move and option buttons and round toggle beside the board, and its round list's rows over it. */
    readonly replayControls: readonly Box[];
    readonly roundList: Box | null;
    /** The replay aside's text: each part's font size and the lines it wraps to; empty on any other page. */
    readonly replayText: readonly ReplayText[];
    /** The replay's narration: its box and how many of its lines its box shows at once; null on any other page. */
    readonly narration: NarrationMeasure | null;
    readonly standings: StandingsMeasure | null;
}

/**
 * The final standings over the board: its panel, the sheet its rounds scroll in, the totals that stick to the sheet's
 * foot, its controls (its ways on and the rounds shown whole in the sheet) and its smallest text.
 */
interface StandingsMeasure {
    readonly panel: Box;
    readonly sheet: Box;
    readonly sheetScroll: Size;
    readonly sheetClient: Size;
    readonly sheetOverflowY: string;
    readonly totals: Box | null;
    readonly controls: readonly Box[];
    readonly minFontPx: number;
    /** A positive and a negative round's cell and result, where the ledger has one: the colour each shows and its tone's. */
    readonly tones: readonly ToneColour[];
}

interface ToneColour {
    readonly cell: string;
    readonly shown: string | null;
    readonly tone: string;
}

interface ReplayText {
    readonly part: string;
    readonly px: number;
    readonly lines: number;
}

interface NarrationMeasure {
    readonly box: Box;
    readonly visibleLines: number;
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
 * The acceptance viewports: two 16:10 desktops and a 16:9 one, the upright phone that gets the rotate panel, the notched landscape phone
 * (its insets cover the plain one), and the smallest supported landscape, which also keeps the aside's scroll honest.
 */
const VIEWPORTS: readonly Viewport[] = [
    {
        context: { viewport: { height: 800, width: 1280 } },
        desktop: true,
        engine: chromium,
        handFloor: { height: 93, width: 70 },
        name: "desktop",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 900, width: 1440 } },
        desktop: true,
        engine: chromium,
        handFloor: { height: 104, width: 78 },
        name: "desktop-1440",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 1080, width: 1920 } },
        desktop: true,
        engine: chromium,
        handFloor: { height: 124, width: 93 },
        name: "desktop-wide",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13"),
        desktop: false,
        engine: webkit,
        handFloor: MIN_TAP,
        name: "phone-portrait",
        portrait: true,
        rotates: true,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13 landscape"),
        desktop: false,
        engine: webkit,
        handFloor: MIN_TAP,
        insets: { bottom: 21, left: 47, right: 47 },
        name: "phone-notch-landscape",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone SE (3rd gen) landscape"),
        desktop: false,
        engine: webkit,
        handFloor: MIN_TAP,
        name: "phone-se-landscape",
        portrait: false,
        rotates: false,
        supported: true,
    },
];

const BOARD_VISIBLE = [
    ".game-board .board-table .tile",
    ".board-local .board-area--bottom-hand .tile",
    ".board-table .nameplate",
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

/** A replay page story: the replay view as on its route, its replay answered from a generated fixture. */
function replayCase(story: string, extra: readonly string[]): PageCase {
    return {
        kind: "board",
        name: `replay-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/replay?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ".replay-controls__moves", ...extra] },
    };
}

/** A replay page story that shows no board: loading, or why the replay cannot be shown. */
function replayStateCase(story: string, content: string): PageCase {
    return documentCase(
        `replay-${story.replaceAll("_", "-")}`,
        `/play/storybook/replay?state=${story}`,
        content,
    );
}

const PAGES: readonly PageCase[] = [
    documentCase("storybook", "/play/storybook", ".storybook .tile"),
    documentCase("storybook-hand", "/play/storybook/hand", ".storybook .hand .tile"),
    documentCase("storybook-discards", "/play/storybook/discards", ".storybook .discards .tile"),
    documentCase("storybook-melds", "/play/storybook/melds", ".storybook .meld .tile"),
    boardCase("board-full-rivers", "?state=full_rivers"),
    boardCase("board-callouts-riichi", "?state=worst&callout=riichi", [".board-callout"]),
    boardCase("board-callouts-tsumo", "?state=full_rivers&callout=tsumo", [".board-callout"]),
    boardCase("board-worst", "?state=worst&pin=right", [
        ".board-strip .meld",
        ".board-dora .tile",
        ".board-center__seat--left .board-center__diff--right",
        ".nameplate__ai",
    ]),
    resultCase("double_ron", "&page=1", [".round-end-result__pager"]),
    resultCase("sanbaiman", "", [".round-end-result__hand .meld"]),
    resultCase("pao", "", [".round-end-result__notes"]),
    resultCase("exhaustive", "", [".round-end-result__tenpai .tile"]),
    boardCase("board-standings", "?overlay=game_end", [
        ".standings__foot-row--leftover",
        ".standings__cell .standings__riichi",
        ".standings__cell .standings__mark--deal-in",
        ".standings__legend",
    ]),
    {
        kind: "board",
        name: "decisions-game-start",
        path: "/play/storybook/decisions?state=game_start",
        required: { visible: [".game-start__seat--viewer", ".game-start__status", ".nameplate"] },
    },
    decisionCase("call_prompt", [ACTION, ".decision-controls__countdown", ".board-cue"]),
    decisionCase("chankan_prompt", [ACTION, ".board-strip .meld"]),
    decisionCase("riichi_pick", [`${ACTION}[aria-pressed="true"]`, ".hand-tile--disabled"]),
    decisionCase("riichi_turn", [
        ACTION,
        ".decision-controls__furiten",
        ".hand-tile--selectable",
        ".decision-controls__bank",
    ]),
    decisionCase("turn_in_bank", [".decision-controls__countdown--bank", ".board-cue"]),
    decisionCase("answered", [".hand-tile--selected"]),
    decisionCase("round_end", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("double_ron_first", [".round-end-result__pager", ".round-end-result__confirm"]),
    decisionCase("waiting", [".round-end-result__waiting"]),
    decisionCase("reconnect_owed", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("last_result", [".round-end-result__confirm"]),
    decisionCase("standings", [
        ".standings__cell--win",
        ".standings__foot-row--result",
        ".standings__actions a[href*='seat=1']",
    ]),
    decisionCase("last_result_reopened", [".round-end-result__confirm"]),
    decisionCase("connection_lost", [".board-notice--warning", ".game-menu__status-word"]),
    decisionCase("move_refused", [".board-notice--warning", ".hand-tile--selectable"]),
    decisionCase("faces_missing", [".board-notice__action", ".hand-tile--selectable"]),
    decisionCase("kicked", [".failure-panel__leave", ".game-menu__status-word"]),
    decisionCase("leave_confirm", [".leave-confirm__leave", ".leave-confirm__stay"]),
    decisionCase("leave_after_win", [".leave-confirm__stay"]),
    {
        countdown: false,
        kind: "panel",
        name: "rotate-waiting",
        path: "/play/storybook/rotate?state=waiting",
        required: { visible: [".rotate-panel", ".rotate-panel .connection-status"] },
    },
    {
        countdown: false,
        kind: "panel",
        name: "rotate-leave",
        path: "/play/storybook/rotate?state=leave",
        required: { visible: [".rotate-panel", ".rotate-panel .leave-confirm__leave"] },
    },
    {
        countdown: false,
        kind: "panel",
        name: "rotate-ended",
        path: "/play/storybook/rotate?state=ended",
        required: { visible: [".rotate-panel", ".rotate-panel .failure-panel__reload"] },
    },
    {
        countdown: true,
        kind: "panel",
        name: "rotate-countdown",
        path: "/play/storybook/rotate?state=countdown",
        required: { visible: [".rotate-panel", ".rotate-panel__seconds"] },
    },
    replayCase("start", [".replay-controls__narration"]),
    replayCase("autoplay", [".replay-controls__option--play[aria-pressed='true']"]),
    replayCase("viewpoint_hidden", [".replay-controls__option--hands[aria-pressed='true']"]),
    replayCase("round_list", [".round-list__row[aria-current]"]),
    replayCase("incomplete", [".replay-controls__incomplete--end"]),
    replayCase("ends_on_result", [".round-end-result__title", ".replay-controls__incomplete--end"]),
    replayCase("damaged", [".replay-controls__incomplete--end"]),
    replayCase("double_ron", [".round-end-result__pager"]),
    replayCase("result_hidden", [
        ".round-end-result__title",
        ".replay-controls__option--hands[aria-pressed='true']",
    ]),
    replayCase("standings", [".standings__round--jump", ".standings__cell--win"]),
    replayCase("standings_long", [".standings__round--jump", ".standings__foot-row--result"]),
    replayStateCase("loading", ".replay-state"),
    replayStateCase("not_found", ".replay-state__links a"),
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

/** The step the replay's controls show within its round, as a number. */
async function replayStep(page: Page): Promise<number> {
    const text = await page.locator(".replay-controls__step").textContent();
    const step = /(?<index>\d+)[/]/u.exec(text ?? "")?.groups?.index;
    if (step === undefined) {
        throw new Error(`the replay shows no step: ${text}`);
    }
    return Number(step);
}

/**
 * Next steps exactly once for each native activation, in the browser's own event order: a click (a press that steps
 * and the click it ends in), and Enter and Space on the focused button, which the page takes as the step.
 */
async function checkStepButton(page: Page): Promise<void> {
    const next = page.locator("[data-step='next']");
    const activations: readonly [string, () => Promise<void>][] = [
        ["a click", () => next.click()],
        ["Enter", () => next.press("Enter")],
        ["Space", () => next.press(" ")],
    ];
    for (const [name, activate] of activations) {
        const before = await replayStep(page);
        await activate();
        const after = await replayStep(page);
        if (after !== before + 1) {
            throw new Error(`${name} on Next stepped from ${before} to ${after}, not once`);
        }
    }
}

async function stepReplayToLocalMelds(page: Page): Promise<void> {
    await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS });
    await checkStepButton(page);
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

/**
 * A context that keeps the run offline and deterministic: reduced motion, so a shot shows each animation's resting
 * state, no web fonts, the handoff set, the socket mocked.
 */
async function openContext(
    browser: Browser,
    viewport: Viewport,
    { frames, origin }: { readonly frames: readonly Uint8Array[]; readonly origin: string },
): Promise<BrowserContext> {
    const context = await browser.newContext({ ...viewport.context, reducedMotion: "reduce" });
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
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function measureStandings(): StandingsMeasure | null {
            const panel = document.querySelector(".board-overlay__panel:has(> .standings)");
            const sheet = panel?.querySelector(".standings__sheet");
            if (panel === null || panel === undefined || sheet === null || sheet === undefined) {
                return null;
            }
            const shown = sheet.getBoundingClientRect();
            const rounds = [...sheet.querySelectorAll(".standings__round--jump")].filter((row) => {
                const { bottom, top } = row.getBoundingClientRect();
                return top >= shown.top && bottom <= shown.bottom;
            });
            const totals = sheet.querySelector("tfoot");
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function toneOf(token: string, within: Element): string {
                const probe = document.createElement("span");
                probe.style.color = `var(${token})`;
                within.append(probe);
                const { color } = getComputedStyle(probe);
                probe.remove();
                return color;
            }
            const toneCells = [
                ["round +", "tbody .standings__cell--positive", "--ronin-score-positive"],
                ["round −", "tbody .standings__cell--negative", "--ronin-score-negative"],
                [
                    "result +",
                    ".standings__foot-row--result .standings__cell--positive",
                    "--ronin-score-positive",
                ],
                [
                    "result −",
                    ".standings__foot-row--result .standings__cell--negative",
                    "--ronin-score-negative",
                ],
            ] as const;
            const tones = toneCells.map(([cell, selector, token]) => {
                const found = sheet.querySelector(selector);
                return {
                    cell,
                    shown: found === null ? null : getComputedStyle(found).color,
                    tone: toneOf(token, panel),
                };
            });
            const texts = [
                ...panel.querySelectorAll(
                    ".standings th, .standings td, .standings__action, .standings__legend-item",
                ),
            ];
            return {
                controls: [...panel.querySelectorAll(".standings__action"), ...rounds].map(box),
                minFontPx: Math.min(
                    ...texts.map((element) =>
                        Number.parseFloat(getComputedStyle(element).fontSize),
                    ),
                ),
                panel: box(panel),
                sheet: box(sheet),
                sheetClient: { height: sheet.clientHeight, width: sheet.clientWidth },
                sheetOverflowY: getComputedStyle(sheet).overflowY,
                sheetScroll: { height: sheet.scrollHeight, width: sheet.scrollWidth },
                tones,
                totals: totals === null ? null : box(totals),
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
        for (const menu of board.querySelectorAll(".board-menu")) {
            grouped.push({ box: box(menu), group: "menu" });
        }
        for (const cue of board.querySelectorAll(".board-cue")) {
            grouped.push({ box: box(cue), group: "cue" });
        }
        const nameplates = [...board.querySelectorAll(".nameplate")].map((plate) => ({
            box: box(plate),
            group: plate.className.split(" ")[1] ?? "nameplate",
        }));
        grouped.push(...nameplates);
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
        const seatTileSelectors: Readonly<Record<string, string>> = {
            bottom: ".board-local .tile",
            left: ".board-strip--left .tile",
            right: ".board-strip--right .tile",
            top: ".board-strip--top .tile",
        };
        const seatTiles = Object.fromEntries(
            Object.entries(seatTileSelectors).map(([seat, selector]) => [
                seat,
                [...board.querySelectorAll(selector)].map(box),
            ]),
        );
        const center = board.querySelector(".board-center");
        const leave = board.querySelector(".game-menu__leave");
        const menu = [...board.querySelectorAll(".game-menu__status, .game-menu__leave")].map(box);
        const roundList = document.querySelector(".round-list");
        const roundRows = document.querySelector(".round-list__rows");
        const shownRows =
            roundRows === null
                ? []
                : [...roundRows.querySelectorAll(".round-list__row")].filter((row) => {
                      const shown = roundRows.getBoundingClientRect();
                      const { bottom, top } = row.getBoundingClientRect();
                      return top >= shown.top && bottom <= shown.bottom;
                  });
        const replayTextParts: Readonly<Record<string, string>> = {
            incomplete: ".replay-controls__incomplete",
            narration: ".replay-controls__narration",
            round: ".replay-controls__round",
        };
        const replayText = Object.entries(replayTextParts).flatMap(([part, selector]) => {
            const element = document.querySelector(selector);
            if (element === null || element.textContent.trim() === "") {
                return [];
            }
            const px = Number.parseFloat(getComputedStyle(element).fontSize);
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const rects: DOMRect[] = [];
            for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
                const range = document.createRange();
                range.selectNodeContents(node);
                rects.push(...[...range.getClientRects()].filter((rect) => rect.height > 0));
            }
            const tops = rects.map((rect) => rect.top).toSorted((first, second) => first - second);
            const lineGap = Math.min(...rects.map((rect) => rect.height)) / 2;
            const lines = tops.filter(
                (top, index) => index === 0 || top - tops[index - 1] > lineGap,
            );
            return [{ lines: lines.length, part, px }];
        });
        const narrationElement = document.querySelector(".replay-controls__narration");
        const narration =
            narrationElement === null
                ? null
                : {
                      box: box(narrationElement),
                      visibleLines: Math.floor(
                          (narrationElement.clientHeight + 1) /
                              Number.parseFloat(getComputedStyle(narrationElement).lineHeight),
                      ),
                  };
        const replayControls = [
            ...document.querySelectorAll(
                ".replay-controls__move, .replay-controls__option, .replay-controls__round, .round-list__close",
            ),
            ...shownRows,
        ].map(box);
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
            callouts: [...board.querySelectorAll(".board-callout")].map(box),
            center: center === null ? null : box(center),
            centerTexts,
            fonts,
            grouped,
            hiddenTiles: tableTiles.filter(
                (tile) =>
                    !tile.checkVisibility({ opacityProperty: true, visibilityProperty: true }),
            ).length,
            leave: leave === null ? null : box(leave),
            localTiles: [
                ...board.querySelectorAll(".board-local .board-area--bottom-hand .tile"),
            ].map(box),
            menu,
            nameplates: nameplates.map((plate) => plate.box),
            narration,
            opponentFaces: [...board.querySelectorAll(".board-strip .tile:not(.tile-back)")].map(
                box,
            ),
            otherTiles: tableTiles
                .filter((tile) => tile.closest(".board-area--bottom-hand, .board-actions") === null)
                .map(box),
            overlay:
                overlay === null
                    ? null
                    : {
                          box: box(overlay),
                          client: { height: overlay.clientHeight, width: overlay.clientWidth },
                          scroll: { height: overlay.scrollHeight, width: overlay.scrollWidth },
                      },
            plates: nameplates.map((plate) => ({
                box: plate.box,
                seat: plate.group.replace("nameplate--", ""),
            })),
            replayControls,
            replayText,
            riverTiles: [
                ...board.querySelectorAll(
                    ".board-river .discard-tile:not(.discard-tile-riichi) .tile",
                ),
            ].map(box),
            roundList: roundList === null ? null : box(roundList),
            seatTiles,
            standings: measureStandings(),
            tiles: tableTiles.map(box),
        };
    }, BOARD_TEXT);
}

/**
 * The text whose size has a floor, and the centre's pieces of text, which must not overlap one another. Each
 * nameplate is an area of its own, so it must not overlap a tile, another plate or the centre.
 */
const BOARD_TEXT = {
    centerTextSelectors: [
        ".board-center__round",
        ".board-center__wall",
        ".board-center__riichi:not(.board-center__riichi--none)",
        ".board-center__score-line",
    ].join(", "),
    fontSelectors: [
        ".board-center__round",
        ".board-center__wall",
        ".board-dora__sticks",
        ".board-dora__label",
        ".board-center__score-line",
        ".nameplate__name",
        ".nameplate__wind",
        ".nameplate__riichi",
        ".nameplate__ai",
        ".board-callout",
        ".board-cue",
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
    const strayPlates = board.nameplates.filter((plate) => !contains(board.board, plate));
    report.expect(strayPlates.length === 0, `${strayPlates.length} nameplate(s) outside the board`);
    const overlaps = findOverlaps(board.grouped);
    report.expect(overlaps.length === 0, `areas overlap: ${overlaps.join(", ")}`);

    const small = board.fonts.filter((font) => font.px < MIN_TEXT_PX);
    report.expect(board.fonts.length > 0, "no board text measured");
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
    const covered = viewport.portrait
        ? []
        : board.menu.filter((control) => intersects(control, overlay.box));
    report.expect(
        covered.length === 0,
        `the overlay panel ${describeBox(overlay.box)} covers the page's corner: ${covered.map(describeBox).join(", ")}`,
    );
    if (viewport.supported) {
        report.expect(
            overlay.scroll.height <= overlay.client.height + EPSILON &&
                overlay.scroll.width <= overlay.client.width + EPSILON,
            `the overlay panel's content overflows it: ${describeSize(overlay.scroll)} > ${describeSize(overlay.client)}`,
        );
    }
}

function longSide(box: Box): number {
    return Math.max(box.width, box.height);
}

/**
 * The local hand stays on the screen, at least the viewport's floor, and its tiles are the board's largest: larger
 * than any river, other seat's hand or meld, or dora tile.
 */
function checkLocalHand(
    board: BoardMeasure,
    { floor, screen }: { readonly floor: Size; readonly screen: Box },
    report: PageReport,
): void {
    const hidden = board.localTiles.filter((tile) => !contains(screen, tile));
    report.expect(hidden.length === 0, `${hidden.length} local hand tile(s) outside the viewport`);
    const small = board.localTiles.filter(
        (tile) => tile.width < floor.width - EPSILON || tile.height < floor.height - EPSILON,
    );
    report.expect(
        small.length === 0,
        `local hand tiles under ${describeSize(floor)}: ${small.map(describeBox).join(", ")}`,
    );
    const smallestOwn = Math.min(...board.localTiles.map(longSide));
    const largestOther = Math.max(0, ...board.otherTiles.map(longSide));
    report.expect(
        smallestOwn > largestOther + EPSILON,
        `a local hand tile (${smallestOwn.toFixed(1)}px) is no larger than another tile on the board (${largestOther.toFixed(1)}px)`,
    );
}

/** The gap between two boxes, 0 when they touch or overlap. */
function gapBetween(first: Box, second: Box): number {
    const dx = Math.max(
        0,
        first.left - (second.left + second.width),
        second.left - (first.left + first.width),
    );
    const dy = Math.max(
        0,
        first.top - (second.top + second.height),
        second.top - (first.top + first.height),
    );
    return Math.hypot(dx, dy);
}

/**
 * Each nameplate reads as its own seat's: close to that seat's tiles, and nearer them than any other seat's. A seat
 * with no tiles (an empty board) is skipped.
 */
function checkPlateOwnership(board: BoardMeasure, report: PageReport): void {
    for (const { box, seat } of board.plates) {
        const distances = Object.entries(board.seatTiles)
            .filter(([, tiles]) => tiles.length > 0)
            .map(([owner, tiles]) => ({
                distance: Math.min(...tiles.map((tile) => gapBetween(box, tile))),
                owner,
            }));
        const own = distances.find((entry) => entry.owner === seat);
        const nearestOther = Math.min(
            ...distances.filter((entry) => entry.owner !== seat).map((entry) => entry.distance),
        );
        report.expect(
            own === undefined ||
                (own.distance <= MAX_PLATE_DISTANCE && own.distance < nearestOther),
            `the ${seat} plate stands ${own?.distance.toFixed(0)}px from its seat's tiles, another seat's at ${nearestOther.toFixed(0)}px`,
        );
    }
}

/** Another seat's face-up tiles stay readable in landscape. */
function checkOpponentFaces(board: BoardMeasure, report: PageReport): void {
    const small = board.opponentFaces.filter(
        (tile) =>
            Math.min(tile.width, tile.height) < MIN_OPPONENT_FACE.width - EPSILON ||
            longSide(tile) < MIN_OPPONENT_FACE.height - EPSILON,
    );
    report.expect(
        small.length === 0,
        `face-up tiles of other seats under ${describeSize(MIN_OPPONENT_FACE)}: ${small.slice(0, 3).map(describeBox).join(", ")}`,
    );
}

/**
 * On a desktop the table keeps the references' proportions: a river tile between a share of the local hand tile's
 * size, and each side seat's hand near the centre, so the board's spare width goes to its margins.
 */
function checkDesktopTable(board: BoardMeasure, report: PageReport): void {
    const [river] = board.riverTiles;
    const [own] = board.localTiles;
    if (river !== undefined && own !== undefined) {
        const ratio = longSide(river) / longSide(own);
        report.expect(
            ratio >= RIVER_TO_HAND.min && ratio <= RIVER_TO_HAND.max,
            `a river tile is ${ratio.toFixed(2)} of a local hand tile, outside ${RIVER_TO_HAND.min}-${RIVER_TO_HAND.max}`,
        );
    }
    const { center } = board;
    const left = board.seatTiles.left ?? [];
    const right = board.seatTiles.right ?? [];
    if (center === null || left.length === 0 || right.length === 0) {
        return;
    }
    const limit = MAX_SIDE_DISTANCE_SHARE * board.board.width;
    const leftGap = center.left - Math.max(...left.map((tile) => tile.left + tile.width));
    const rightGap = Math.min(...right.map((tile) => tile.left)) - (center.left + center.width);
    report.expect(
        leftGap <= limit && rightGap <= limit,
        `a side hand stands ${Math.max(leftGap, rightGap).toFixed(0)}px from the centre, over ${limit.toFixed(0)}px`,
    );
}

/** The wall count and the sticks read at no less than a share of the scores' size. */
function fontSizes(board: BoardMeasure, name: string): number[] {
    return board.fonts.filter((font) => font.name === name).map((font) => font.px);
}

function checkCounters(board: BoardMeasure, report: PageReport): void {
    const score = Math.max(0, ...fontSizes(board, "board-center__score-line"));
    const smallest = Math.min(
        ...fontSizes(board, "board-center__wall"),
        ...fontSizes(board, "board-dora__sticks"),
    );
    report.expect(
        smallest >= MIN_COUNTER_TO_SCORE * score - EPSILON,
        `a counter reads ${smallest}px beside ${score}px scores`,
    );
}

/** The page's way back sits on the board and the screen, large enough to tap. */
function checkLeave(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { leave } = board;
    if (leave === null) {
        return;
    }
    report.expect(
        contains(board.board, leave) && contains(screen, leave),
        `the leave button ${describeBox(leave)} is off the board or screen`,
    );
    report.expect(
        leave.width >= MIN_ACTION_SIZE - EPSILON && leave.height >= MIN_ACTION_SIZE - EPSILON,
        `the leave button is under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${describeBox(leave)}`,
    );
}

/** The replay's controls sit on the screen, large enough to tap, and its round list on the board. */
function checkReplayControls(board: BoardMeasure, screen: Box, report: PageReport): void {
    const outside = board.replayControls.filter((control) => !contains(screen, control));
    report.expect(outside.length === 0, `${outside.length} replay control(s) off the screen`);
    const small = board.replayControls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `replay controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    if (board.roundList !== null) {
        report.expect(
            contains(board.board, board.roundList),
            `the round list ${describeBox(board.roundList)} leaves the board`,
        );
    }
}

/**
 * The final standings fit their panel: the rounds scroll inside the sheet rather than past the board, and in landscape
 * never sideways (an upright page may scroll), the totals stay in view at the sheet's foot, no text is under the
 * floor, and on a supported landscape screen every control (its ways on, the rounds shown) is on the screen and large
 * enough to tap.
 */
function checkStandings(
    board: BoardMeasure,
    { screen, viewport }: { readonly screen: Box; readonly viewport: Viewport },
    report: PageReport,
): void {
    const { standings } = board;
    if (standings === null) {
        return;
    }
    const scrolls = standings.sheetScroll.height > standings.sheetClient.height + EPSILON;
    report.expect(
        !scrolls || standings.sheetOverflowY === "auto" || standings.sheetOverflowY === "scroll",
        "the standings' rounds overflow their sheet with no way to scroll to them",
    );
    report.expect(
        viewport.portrait || standings.sheetScroll.width <= standings.sheetClient.width + EPSILON,
        `the standings' sheet scrolls sideways: ${describeSize(standings.sheetScroll)} > ${describeSize(standings.sheetClient)}`,
    );
    report.expect(
        contains(standings.panel, standings.sheet),
        `the standings' sheet ${describeBox(standings.sheet)} leaves its panel`,
    );
    report.expect(
        standings.totals !== null && contains(standings.sheet, standings.totals),
        "the standings' totals are not in view at the sheet's foot",
    );
    const toned = standings.tones.filter(({ shown }) => shown !== null);
    const offTone = toned.filter(({ shown, tone }) => shown !== tone);
    report.expect(
        toned.length > 0 && offTone.length === 0,
        `standings cells not in their tone: ${offTone.map(({ cell, shown, tone }) => `${cell} ${shown} for ${tone}`).join(", ") || "none to check"}`,
    );
    report.expect(
        standings.minFontPx >= MIN_TEXT_PX,
        `standings text at ${standings.minFontPx}px, under ${MIN_TEXT_PX}px`,
    );
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    const outside = standings.controls.filter(
        (control) => !contains(screen, control) || !contains(standings.panel, control),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} standings control(s) off the panel or screen`,
    );
    const small = standings.controls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `standings controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
}

/** On a desktop the replay's aside reads at a glance: its narration and round, and its incompleteness label. */
function checkReplayText(board: BoardMeasure, report: PageReport): void {
    for (const { lines, part, px } of board.replayText) {
        const limit = REPLAY_TEXT_LIMITS[part];
        report.expect(
            px >= limit.px && lines <= limit.lines,
            `the replay's ${part} at ${px}px on ${lines} line(s), past ${limit.px}px on ${limit.lines}`,
        );
    }
}

/**
 * On a landscape phone the replay's column keeps room for its narration, at least three lines in view at once
 * whatever else the column holds, and the narration wholly on the screen and inside the column.
 */
function checkPhoneNarration(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { aside, narration } = board;
    if (narration === null || aside === null) {
        return;
    }
    report.expect(
        narration.visibleLines >= MIN_PHONE_NARRATION_LINES,
        `the replay's narration shows ${narration.visibleLines} line(s) at once, under ${MIN_PHONE_NARRATION_LINES}`,
    );
    report.expect(
        contains(screen, narration.box) && contains(aside.box, narration.box),
        `the replay's narration ${describeBox(narration.box)} leaves the screen or its column`,
    );
}

/** A call shown by its seat stays on the board and never lies over the local hand's tiles, which take the taps. */
function checkCallouts(board: BoardMeasure, report: PageReport): void {
    const outside = board.callouts.filter((callout) => !contains(board.board, callout));
    report.expect(outside.length === 0, `${outside.length} call(s) off the board`);
    const overHand = board.callouts.filter((callout) =>
        board.localTiles.some((tile) => intersects(callout, tile)),
    );
    report.expect(
        overHand.length === 0,
        `call(s) over the local hand: ${overHand.map(describeBox).join(", ")}`,
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
    checkCallouts(board, report);
    checkStandings(board, { screen, viewport }, report);
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
        checkLocalHand(board, { floor: viewport.handFloor, screen }, report);
        checkActions(board, screen, report);
        checkLeave(board, screen, report);
        checkReplayControls(board, screen, report);
        checkOpponentFaces(board, report);
        checkPlateOwnership(board, report);
        checkCounters(board, report);
    }
    if (viewport.desktop) {
        checkDesktopTable(board, report);
        checkReplayText(board, report);
    } else if (viewport.supported && !viewport.portrait) {
        checkPhoneNarration(board, screen, report);
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
    const title = ".rotate-panel__title, .rotate-panel .failure-panel__title";
    const wayBack = [
        ".rotate-panel__leave:not([hidden])",
        ".rotate-panel .leave-confirm__leave",
        ".rotate-panel .failure-panel__leave",
    ].join(", ");
    await checkVisible(page, [title, wayBack], report);
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

/** The tile faces a page draws: every face's sprite symbol, with content, and whether a shown face drew a box. */
interface TileFaces {
    readonly count: number;
    readonly unresolved: readonly string[];
    readonly drawn: boolean;
}

/**
 * Fail a page whose tile sprite never loaded, or whose faces name a symbol the sprite lacks or holds empty: either
 * leaves the faces blank, which a layout check alone passes.
 */
async function checkTileFaces(page: Page, report: PageReport): Promise<void> {
    const loaded = await page
        .waitForFunction(() => document.documentElement.dataset.tileSprite === "ready", null, {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(loaded, "the tile sprite did not load");
    const faces = await page.evaluate((): TileFaces => {
        const uses = [...document.querySelectorAll(".tile svg use")].filter(
            (use) => use instanceof SVGUseElement,
        );
        const unresolved = uses
            .map((use) => use.getAttribute("href") ?? "")
            .filter(
                (href) => (document.querySelector(`symbol${href}`)?.childElementCount ?? 0) === 0,
            );
        const shown = uses.filter((use) => use.closest("svg")?.checkVisibility() === true);
        const drawn =
            shown.length === 0 ||
            shown.some((use) => {
                const bounds = use.getBBox();
                return bounds.width > 0 && bounds.height > 0;
            });
        return { count: uses.length, drawn, unresolved: [...new Set(unresolved)] };
    });
    if (faces.count === 0) {
        return;
    }
    report.expect(
        faces.unresolved.length === 0,
        `tile faces with no sprite symbol: ${faces.unresolved.join(", ")}`,
    );
    report.expect(faces.drawn, "no tile face drew");
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
        await checkTileFaces(page, report);
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

/** The pages and viewports a run checks: all of them, or the ones `--page` and `--viewport` name. */
interface Selection {
    readonly pages: readonly PageCase[];
    readonly viewports: readonly Viewport[];
    readonly partial: boolean;
}

/** The selected pages at each of an engine's selected viewports. */
function tasksOf(engine: BrowserType, selection: Selection): PageTask[] {
    const viewports = selection.viewports.filter((viewport) => viewport.engine === engine);
    return viewports.flatMap((viewport) =>
        selection.pages.map((pageCase) => ({ pageCase, viewport })),
    );
}

/** Check an engine's tasks in one browser, several pages at once. */
async function runEngine(
    browser: Browser,
    tasks: readonly PageTask[],
    run: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult[]> {
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

/** Both engines' pages at once, then, on a full run, the replay load budget on the Chromium browser, the CPU idle. */
async function checkAll(
    fixtures: Fixtures,
    shots: string,
    selection: Selection,
): Promise<string[]> {
    const [chromiumBrowser, webkitBrowser] = await Promise.all([
        chromium.launch(),
        webkit.launch(),
    ]);
    try {
        const run = { fixtures, shots };
        const results = await Promise.all([
            runEngine(chromiumBrowser, tasksOf(chromium, selection), run),
            runEngine(webkitBrowser, tasksOf(webkit, selection), run),
        ]);
        const pageFailures = reportFailures(results.flat());
        if (selection.partial) {
            return pageFailures;
        }
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

/** Keep the items whose name contains one of `filters`, or every item when there are none. */
function matching<Item extends { readonly name: string }>(
    items: readonly Item[],
    filters: readonly string[],
): readonly Item[] {
    if (filters.length === 0) {
        return items;
    }
    return items.filter((item) => filters.some((filter) => item.name.includes(filter)));
}

/** The run's selection from `--page` and `--viewport` (each repeatable, matching a name by substring). */
function selectRun(pageFilters: readonly string[], viewportFilters: readonly string[]): Selection {
    return {
        pages: matching(PAGES, pageFilters),
        partial: pageFilters.length > 0 || viewportFilters.length > 0,
        viewports: matching(VIEWPORTS, viewportFilters),
    };
}

async function main(): Promise<number> {
    const { values } = parseArgs({
        options: {
            page: { default: [], multiple: true, type: "string" },
            shots: { default: DEFAULT_SHOTS, type: "string" },
            viewport: { default: [], multiple: true, type: "string" },
        },
    });
    const selection = selectRun(values.page, values.viewport);
    if (selection.pages.length === 0 || selection.viewports.length === 0) {
        console.error(
            `Visual check selected nothing: pages ${PAGES.map(({ name }) => name).join(", ")}; viewports ${VIEWPORTS.map(({ name }) => name).join(", ")}`,
        );
        return 1;
    }
    const shots = resolve(values.shots);
    if (shots === DEFAULT_SHOTS) {
        await clearShots(shots);
    }
    const frames = await transcriptFrames();
    const { origin, server } = await startServer();
    const failures = await checkAll({ frames, origin }, shots, selection).finally(() =>
        server.close(),
    );
    if (failures.length > 0) {
        console.error(
            `Visual check failed:\n${failures.map((failure) => `  ${failure}`).join("\n")}`,
        );
        return 1;
    }
    const pages = selection.viewports.length * selection.pages.length;
    const scope = selection.partial ? "partial run, no replay load budget; " : "";
    console.info(`Visual check passed: ${scope}${pages} pages; screenshots in ${shots}`);
    return 0;
}

process.exitCode = await main();
